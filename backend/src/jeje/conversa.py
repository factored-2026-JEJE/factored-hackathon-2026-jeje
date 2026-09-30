"""Conversa sem modelo (G10): um turno = interpretar → política → ação verificada → resposta.

O estado da conversa fica no banco, travado durante o turno, sempre de um cliente da sessão; a
leitura da mensagem, que pode esperar o modelo, vem antes e fora da transação (ACH-030).
Nenhum turno pula a política: o texto só escolhe a pergunta feita a ela, e a transação só vem de
consulta filtrada pelo dono. Efeito (pré-caso) só com confirmação explícita ligada à proposta
guardada no estado; encaminhamento humano grava o resumo e encerra a automação da conversa.

Cada estado espera uma coisa: um pedido (livre), a transação (esclarecendo: pistas somam entre os
turnos, o status citado é pista e não filtro), o sim ou não (confirmando) ou algo sobre a transação
já respondida (livre com foco). O que não cabe na etapa é respondido com o que foi entendido e a
oferta do atendente: o sim encaminha, o não volta à etapa, e outra mensagem é lida nela. A
pergunta pelo pedido de revisão já registrado (status do caso) é respondida em qualquer etapa.
Falha ao gravar propaga: quem chama desfaz o turno inteiro, sem resposta de sucesso.
"""

import json
import secrets
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from functools import cached_property
from typing import Literal

from sqlalchemy import Connection, text

from jeje import consultas, eventos, handoff, politica, pre_caso
from jeje.interpretacao import Interpretacao, comercio_citado
from jeje.interpretacao_modelo import Interpretador, Leitura, pelas_regras
from jeje.mensagens import (
    ESTADO,
    ESTADO_DO_CASO,
    MOTIVO_DO_CODIGO,
    PEDIDO,
    Idioma,
    TransacaoVerificada,
    compor,
    descrever,
    marcadores,
)
from jeje.models import ESTADOS_DA_CONVERSA

Estado = Literal[ESTADOS_DA_CONVERSA]
# Estados em que a automação não age mais: com humano (só lembra quem está com o caso) ou
# encerrada pela recarga dos dados. O modelo não é chamado, e a recarga não os toca.
TERMINAIS: frozenset[Estado] = frozenset({"com_humano", "encerrada"})

LIMITE_MENSAGEM = 500
MAXIMO_OPCOES = 5

# O que fica para o atendente resolver, por regra que encaminhou (texto interno, em português).
PENDENCIAS = {
    "POL-HUM-01": "Tratar relato de fraude: bloqueio e análise do cartão",
    "POL-HUM-02": "Revisar contestação que a automação não pode registrar",
    "POL-HUM-04": "Revisar contestação de transação noturna por celular ou computador",
    "POL-HUM-05": "Revisar contestação de compra fora da janela de contestação",
    "POL-HUM-06": "Revisar contestação de cliente com vários pré-casos recentes",
    "POL-SEG-01": "Análise de segurança de transferência de alto valor",
    "POL-HUM-03": "Atender o cliente no pedido abaixo",
    "POL-DISP-02": "Orientar sobre contestação de transação não aprovada",
    "POL-CON-04": "Explicar transação sem status ou motivo reconhecido",
}
# Cláusula mostrada ao cliente quando a regra encaminha para humano.
CLAUSULA_DO_HUMANO = {"POL-CON-04": "POL-HUM-02"}


class ConversaNaoEncontrada(Exception):
    """Conversa inexistente ou de outro cliente (indistinguíveis para quem pergunta)."""


@dataclass(frozen=True)
class Opcao:
    numero: int
    transaction_id: str
    descricao: str


@dataclass(frozen=True)
class Saida:
    """O que o turno decidiu, antes de ser gravado."""

    regra: str
    acao: str
    textos: tuple[str, ...]
    estado: Estado
    contexto: dict = field(default_factory=dict)
    transaction_id: str | None = None
    opcoes: tuple[Opcao, ...] = ()
    proposta: pre_caso.Proposta | None = None
    protocolo: str | None = None
    atendimento: str | None = None


@dataclass(frozen=True)
class ResultadoDoTurno:
    conversa_id: str
    numero: int
    idioma: Idioma
    intencao: str
    saida: Saida

    @property
    def resposta(self) -> str:
        return "\n".join(self.saida.textos)

    @property
    def efeito(self) -> str | None:
        return _efeito(self.saida)


def verificada(t: consultas.Transacao) -> TransacaoVerificada:
    return TransacaoVerificada(
        t.transaction_id,
        t.transaction_date,
        t.amount,
        t.currency,
        t.merchant_name,
        t.transaction_status,
    )


def texto(regra: str, idioma: Idioma, t: TransacaoVerificada | None = None, **extra: str) -> str:
    """Cláusula aprovada preenchida só com os fatos que ela pede (de transação verificada)."""
    disponiveis: dict[str, str] = dict(extra)
    if t is not None:
        disponiveis["transacao"] = descrever(t, idioma)
        if t.transaction_status in ESTADO:
            disponiveis["estado"] = ESTADO[t.transaction_status][idioma]
    return compor(regra, idioma, **{m: disponiveis[m] for m in marcadores(regra, idioma)})


def _do_dono(
    conexao: Connection, customer_id: str, conversa_id: str, colunas: str, travar: bool = False
):
    """Linha da conversa, só se ela for do cliente da sessão: a de outro cliente é igual a
    inexistente (R08). `travar` segura a conversa até o fim da transação (um turno por vez)."""
    linha = conexao.execute(
        text(
            f"SELECT {colunas} FROM app.conversas WHERE id = :id AND customer_id = :cliente"
            + (" FOR UPDATE" if travar else "")
        ),
        {"id": conversa_id, "cliente": customer_id},
    ).first()
    if linha is None:
        raise ConversaNaoEncontrada(conversa_id)
    return linha


def abrir(conexao: Connection, customer_id: str, idioma: Idioma) -> tuple[str, str]:
    """Nova conversa do cliente da sessão; devolve (id, saudação)."""
    conversa_id = secrets.token_urlsafe(16)
    conexao.execute(
        text("INSERT INTO app.conversas (id, customer_id, idioma) VALUES (:id, :cliente, :idioma)"),
        {"id": conversa_id, "cliente": customer_id, "idioma": idioma},
    )
    return conversa_id, compor("SAUDACAO", idioma)


class _Turno:
    def __init__(
        self,
        conexao: Connection,
        customer_id: str,
        estado: Estado,
        contexto: dict,
        lida: Interpretacao,
        mensagem: str,
        limites: politica.Limites,
        ttl_minutos: int,
    ) -> None:
        self.conexao, self.customer_id = conexao, customer_id
        self.estado, self.contexto = estado, contexto
        self.lida, self.mensagem, self.idioma = lida, mensagem, lida.idioma
        self.limites, self.ttl_minutos = limites, ttl_minutos
        self.acoes: list[handoff.Acao] = [handoff.Acao(**a) for a in contexto.get("acoes", [])]
        self.fontes: dict[str, None] = {}  # de onde vieram os fatos e onde houve escrita (trace)

    # ---- entrada -----------------------------------------------------------------------------

    def executar(self) -> Saida:
        if self.estado == "encerrada":
            # A recarga dos dados encerrou a conversa: nada do contexto vale mais (PRD-002).
            aviso = texto("ENCERRADA", self.idioma)
            return Saida("ENCERRADA", "encerrada", (aviso,), "encerrada")
        if self.estado == "com_humano":
            # A automação não responde mais nada: só lembra quem está com o caso.
            atendimento = self.contexto["atendimento"]
            return Saida(
                "COM-HUMANO",
                "aguardar_humano",
                (texto("COM-HUMANO", self.idioma, atendimento=atendimento),),
                "com_humano",
                self.contexto,
                atendimento=atendimento,
            )
        decisao = politica.decidir_pedido(self.lida.intencao, self.lida.id_digitado)
        if decisao is not None and decisao.acao == "humano":
            # Segurança e pedido de atendente valem em qualquer etapa.
            self._anotar("interpretar", f"{decisao.regra}: {', '.join(self.lida.sinais)}")
            return self._encaminhar(decisao, self._em_foco())
        if self._resumiu() and self.lida.resposta is None:
            # Respondeu ao resumo com outra coisa: volta à etapa e a mensagem é lida nela.
            self.estado, self.contexto = self._etapa_resumida()
        if self.estado == "confirmando" and self.lida.resposta is not None:
            return self._confirmar() if self.lida.resposta == "sim" else self._cancelar()
        if self.estado == "oferecendo_humano" and self.lida.resposta is not None:
            if self.lida.resposta == "nao":
                return self._retomar() if self._resumiu() else self._cancelar()
            aceito = politica.Decisao("POL-HUM-03", "humano", "aceitou o atendente oferecido")
            return self._encaminhar(aceito, self._em_foco())
        if self.lida.cortesia is not None:
            # Cumprimento ou agradecimento: resposta cordial, sem recusa nem resumo.
            return self._cortesia()
        if self.lida.caso and self.lida.intencao != "fora_de_escopo":
            # Pergunta pelo pedido de revisão, em qualquer etapa. Protocolo digitado só indica o
            # assunto: a resposta sai dos pré-casos do cliente da sessão, nunca do que foi digitado.
            return self._status_do_caso()
        if decisao is not None and decisao.regra == "POL-ID-02":
            # Identificador digitado não desfaz o que estava pendente.
            recusa = texto(decisao.regra, self.idioma)
            return Saida(decisao.regra, "recusar", (recusa,), self.estado, self.contexto)
        fora_de_escopo = decisao is not None
        if self.estado == "esclarecendo" and (escolhida := self._escolhida()) is not None:
            return self._agir(self.contexto["intencao"], escolhida)
        if self._pista_da_etapa():
            # Pista enquanto se procura a transação é do pedido em andamento, qualquer que seja a
            # palavra que a acompanha ("la compra del 10/03" numa contestação segue contestação).
            contestar = self.lida.intencao == "contestar"
            intencao = "contestar" if contestar else self.contexto.get("intencao", "contestar")
            return self._resolver(intencao, novo_assunto=False)
        if not fora_de_escopo and self.lida.intencao in ("consultar", "contestar"):
            return self._pedido(self.lida.intencao)
        if not fora_de_escopo and self._tem_pista():
            return self._pedido("consultar")
        if self._em_etapa():
            # Nada do que a etapa espera (nem pedido novo): diz o que entendeu e oferece o
            # atendente, em vez de repetir a pergunta ou recusar.
            return self._resumir_etapa()
        if fora_de_escopo:
            fora = (texto("POL-ESC-01", self.idioma), texto("OFERTA-FORA", self.idioma))
            return self._oferecer(fora, decisao.regra, "livre", {})
        return self._nao_entendido()

    # ---- etapas ------------------------------------------------------------------------------

    def _em_etapa(self) -> bool:
        """Esperando a transação, a confirmação ou falando de uma transação já respondida."""
        return self.estado in ("esclarecendo", "confirmando") or "foco" in self.contexto

    def _pista_da_etapa(self) -> bool:
        """Pista (valor, data ou comércio) enquanto se procura ou confirma a transação. Status
        citado ("¿y la rechazada?") é pergunta nova, não pista do pedido em andamento."""
        return (
            self.estado in ("esclarecendo", "confirmando")
            and self.lida.status is None
            and self._tem_pista()
        )

    def _resumiu(self) -> bool:
        return self.estado == "oferecendo_humano" and "etapa" in self.contexto

    def _etapa_resumida(self) -> tuple[Estado, dict]:
        etapa = self.contexto["etapa"]
        return etapa["estado"], etapa["contexto"]

    def _resumir_etapa(self) -> Saida:
        if self.estado == "esclarecendo":
            pedido = PEDIDO[self.contexto["intencao"]][self.idioma]
            resumo = texto("RESUMO-TRANSACAO", self.idioma, pedido=pedido)
        elif self.estado == "confirmando":
            t = self._verificada(self.contexto["transaction_id"])
            resumo = texto("RESUMO-CONFIRMACAO", self.idioma, t)
        else:
            resumo = texto("RESUMO-FOCO", self.idioma, self._verificada(self.contexto["foco"]))
        oferta = texto("OFERTA-ATENDENTE", self.idioma)
        return self._oferecer((resumo, oferta), "RESUMO", self.estado, self.contexto)

    def _oferecer(
        self, textos: tuple[str, ...], regra: str, estado: Estado, contexto: dict
    ) -> Saida:
        """Oferece o atendente guardando a etapa: "sí" encaminha, "no" volta a ela, e qualquer
        outra mensagem é lida nela."""
        transaction_id = contexto.get("transaction_id") or contexto.get("foco")
        oferta = {
            "etapa": {"estado": estado, "contexto": contexto},
            "pedido": contexto.get("pedido", self.mensagem[:280]),
            "acoes": self._acoes_json(),
        }
        if transaction_id is not None:
            oferta["transaction_id"] = transaction_id
        return Saida(
            regra,
            "oferecer_humano",
            textos,
            "oferecendo_humano",
            oferta,
            transaction_id=transaction_id,
        )

    def _retomar(self) -> Saida:
        """Recusou o atendente oferecido no resumo: volta à etapa e repete o que ela pergunta."""
        self.estado, self.contexto = self._etapa_resumida()
        aviso = texto("RETOMAR", self.idioma)
        if self.estado == "esclarecendo":
            self.contexto = {**self.contexto, "esclarecimentos": 0}
            pergunta = self._perguntar(self.contexto["intencao"], None)
            return replace(pergunta, textos=(aviso, *pergunta.textos))
        if self.estado == "confirmando":
            pendente = self._confirmacao_pendente()
            return replace(pendente, textos=(aviso, *pendente.textos))
        contexto = _so_foco(self.contexto.get("foco"))
        livre = texto("RETOMAR-LIVRE", self.idioma)
        return Saida("RETOMAR", "responder", (livre,), "livre", contexto)

    def _confirmacao_pendente(self) -> Saida:
        transaction_id = self.contexto["transaction_id"]
        pergunta = texto("CONFIRMACAO-PENDENTE", self.idioma, self._verificada(transaction_id))
        return Saida(
            "POL-DISP-01",
            "confirmar",
            (pergunta,),
            "confirmando",
            self.contexto,
            transaction_id=transaction_id,
        )

    def _nao_entendido(self) -> Saida:
        """Mensagem não entendida também é esclarecimento (POL-HUM-03): pede de novo até o limite
        e depois oferece o atendente, com a primeira mensagem da sequência no resumo. Pedido
        entendido zera a contagem (o contexto é trocado)."""
        pedidos_de_novo = self.contexto.get("esclarecimentos", 0)
        decisao = politica.decidir_esclarecimento(pedidos_de_novo)
        pedido = self.contexto.get("pedido", self.mensagem[:280])
        if decisao.acao == "oferecer_humano":
            self._anotar("esclarecer", f"{pedidos_de_novo} mensagens seguidas não entendidas")
            resumo = (texto("RESUMO-PEDIDO", self.idioma),)
            return self._oferecer(resumo, decisao.regra, "livre", {"pedido": pedido})
        contexto = {"pedido": pedido, "esclarecimentos": pedidos_de_novo + 1}
        return Saida("AJUDA", "esclarecer", (texto("AJUDA", self.idioma),), "livre", contexto)

    # ---- resolução da transação --------------------------------------------------------------

    def _tem_pista(self) -> bool:
        lida = self.lida
        pistas = (lida.valor, lida.data, lida.status, self._comercio)
        return lida.ultima or any(p is not None for p in pistas)

    def _pedido(self, intencao: str) -> Saida:
        """Novo pedido: sem pista, vale a transação em foco (a última de que se falou)."""
        foco = self.contexto.get("foco")
        if foco is not None and not self._tem_pista():
            return self._agir(intencao, foco)
        return self._resolver(intencao, novo_assunto=True)

    def _candidatas(self, status: str | None) -> list[politica.Candidata]:
        self._fonte("curated.transactions")
        return consultas.candidatas_do_cliente(self.conexao, self.customer_id, status)

    @cached_property
    def _comercio(self) -> str | None:
        """Comércio citado, entre os das transações do próprio cliente."""
        comercios = consultas.comercios_do_cliente(self.conexao, self.customer_id)
        return comercio_citado(self.mensagem, comercios)

    def _resolver(self, intencao: str, novo_assunto: bool) -> Saida:
        if novo_assunto:
            self.contexto = {"pedido": self.mensagem[:280], "status": self.lida.status}
            self.acoes = []
        status = self.lida.status or self.contexto.get("status")
        if intencao == "contestar":
            status = None  # contestação vale para qualquer status; a política decide
        pista = self._pista()
        if not novo_assunto:
            # O que ainda falta se preenche ao longo da etapa: as pistas de antes somam com as de
            # agora ("fue en Cine Premium", depois "la de 45,90").
            pista = _somar(_pista_do_contexto(self.contexto.get("pista")), pista)
        resolucao = self._resolucao(status, pista)
        if resolucao.tipo == "nenhuma" and not novo_assunto and pista != (atual := self._pista()):
            # A soma não casa nada (uma pista de antes estava errada): vale a mensagem de agora.
            pista, resolucao = atual, self._resolucao(status, atual)
        if resolucao.tipo == "unica":
            return self._agir(intencao, resolucao.transacoes[0])
        return self._perguntar(intencao, resolucao.transacoes, pista)

    def _pista(self) -> politica.Pista:
        return politica.Pista(self.lida.valor, self.lida.data, self._comercio, self.lida.ultima)

    def _resolucao(self, status: str | None, pista: politica.Pista) -> politica.Resolucao:
        resolucao = politica.resolver_transacao(self._candidatas(status), pista, MAXIMO_OPCOES)
        if resolucao.tipo == "nenhuma" and status is not None and pista != politica.Pista():
            # O status citado é pista, não filtro: "¿por qué rechazaron la de Boutique Moda?"
            # sobre uma aprovada acha a aprovada, e a resposta diz o status verdadeiro.
            resolucao = politica.resolver_transacao(self._candidatas(None), pista, MAXIMO_OPCOES)
        return resolucao

    def _perguntar(
        self,
        intencao: str,
        opcoes_ids: tuple[str, ...] | None,
        pista: politica.Pista | None = None,
    ) -> Saida:
        """Pergunta qual transação (ou pede dados, se nenhuma casou); `None` repete as opções já
        apresentadas. Passado o limite de esclarecimentos, diz o que entendeu e oferece o
        atendente (POL-HUM-03); o "não" volta a esta pergunta."""
        feitos = self.contexto.get("esclarecimentos", 0)
        decisao = politica.decidir_esclarecimento(feitos)
        if opcoes_ids is None:
            opcoes_ids = tuple(self.contexto.get("opcoes", ()))
        opcoes = tuple(
            Opcao(n, tid, descrever(self._verificada(tid), self.idioma))
            for n, tid in enumerate(opcoes_ids, start=1)
        )
        contexto = {
            "pedido": self.contexto.get("pedido", self.mensagem[:280]),
            "status": self.contexto.get("status"),
            "intencao": intencao,
            "opcoes": [o.transaction_id for o in opcoes],
            "esclarecimentos": feitos + 1,
            "acoes": self._acoes_json(),
        }
        if pista is not None or "pista" in self.contexto:
            contexto["pista"] = _pista_json(pista) if pista is not None else self.contexto["pista"]
        if decisao.acao == "oferecer_humano":
            self._anotar("esclarecer", f"{feitos} perguntas sem identificar a transação")
            pedido = PEDIDO[intencao][self.idioma]
            resumo = texto("RESUMO-TRANSACAO", self.idioma, pedido=pedido)
            textos = (resumo, texto("OFERTA-ATENDENTE", self.idioma))
            return self._oferecer(textos, decisao.regra, "esclarecendo", contexto)
        if not opcoes:
            pedido_de_dados = texto("CON-NENHUMA", self.idioma)
            return Saida("POL-CON-02", "esclarecer", (pedido_de_dados,), "esclarecendo", contexto)
        lista = "\n".join(f"{o.numero}. {o.descricao}" for o in opcoes)
        pergunta = texto("POL-CON-02", self.idioma, opcoes=lista)
        return Saida(
            "POL-CON-02", "esclarecer", (pergunta,), "esclarecendo", contexto, opcoes=opcoes
        )

    def _escolhida(self) -> str | None:
        opcoes = self.contexto.get("opcoes", [])
        escolha = self.lida.escolha
        if escolha is not None and 1 <= escolha <= len(opcoes):
            return opcoes[escolha - 1]
        return None

    def _do_cliente(self, transaction_id: str) -> TransacaoVerificada | None:
        """A transação, se ela for do cliente da sessão na curada atual; senão, None."""
        self._fonte("curated.transactions")
        t = consultas.transacao_do_cliente(self.conexao, self.customer_id, transaction_id)
        return None if t is None else verificada(t)

    def _verificada(self, transaction_id: str) -> TransacaoVerificada:
        t = self._do_cliente(transaction_id)
        if t is None:  # só chegam aqui IDs lidos da curada para este cliente
            raise LookupError("transação do contexto não pertence ao cliente da sessão")
        return t

    def _em_foco(self) -> TransacaoVerificada | None:
        tid = self.contexto.get("transaction_id") or self.contexto.get("foco")
        return None if tid is None else self._verificada(tid)

    # ---- ações -------------------------------------------------------------------------------

    def _agir(self, intencao: str, transaction_id: str) -> Saida:
        t = self._verificada(transaction_id)
        self._anotar("identificar_transacao", f"{t.transaction_id} ({t.transaction_status})")
        if intencao == "contestar":
            return self._contestar(t)
        return self._consultar(t)

    def _consultar(self, t: TransacaoVerificada) -> Saida:
        fatos = consultas.fatos_da_transacao(self.conexao, self.customer_id, t.transaction_id)
        decisao = politica.decidir_consulta(fatos, self.limites)
        self._anotar("consultar_situacao", decisao.regra)
        if decisao.acao == "humano":
            return self._encaminhar(decisao, t)
        extra = {}
        if decisao.regra == "POL-CON-03":
            codigo = decisao.detalhe
            extra = {"codigo": codigo, "motivo": MOTIVO_DO_CODIGO[codigo][self.idioma]}
        resposta = texto(decisao.regra, self.idioma, t, **extra)
        # Recusa sem motivo registrado: a cláusula oferece atendente; o próximo "sí" aceita.
        oferece = decisao.regra == "POL-CON-04"
        contexto = {"foco": t.transaction_id}
        if oferece:
            contexto |= {"transaction_id": t.transaction_id, "acoes": self._acoes_json()}
        return Saida(
            decisao.regra,
            "responder",
            (resposta,),
            "oferecendo_humano" if oferece else "livre",
            contexto,
            transaction_id=t.transaction_id,
        )

    def _contestar(self, t: TransacaoVerificada) -> Saida:
        decisao, proposta = pre_caso.propor(
            self.conexao, self.customer_id, t.transaction_id, self.limites, self.ttl_minutos
        )
        self._anotar("avaliar_contestacao", f"{decisao.regra}: {decisao.detalhe or decisao.acao}")
        self._fonte("app.pre_casos")
        if proposta is not None:
            self._fonte("app.propostas_pre_caso")
            contexto = {
                "proposta_id": proposta.id,
                "transaction_id": t.transaction_id,
                "foco": t.transaction_id,
                "acoes": self._acoes_json(),
            }
            return Saida(
                decisao.regra,
                "propor_pre_caso",
                (texto(decisao.regra, self.idioma, t),),
                "confirmando",
                contexto,
                transaction_id=t.transaction_id,
                proposta=proposta,
            )
        if decisao.acao == "humano":
            return self._encaminhar(decisao, t)
        protocolo = decisao.detalhe  # POL-DISP-03: pré-caso já existente, relido do banco
        return Saida(
            decisao.regra,
            "responder",
            (texto(decisao.regra, self.idioma, t, protocolo=protocolo),),
            "livre",
            {"foco": t.transaction_id},
            transaction_id=t.transaction_id,
            protocolo=protocolo,
        )

    def _confirmar(self) -> Saida:
        """Confirmação explícita da proposta guardada no estado (nunca de outra)."""
        proposta_id, transaction_id = self.contexto["proposta_id"], self.contexto["transaction_id"]
        self._fonte("app.pre_casos")
        try:
            registrado, _ = pre_caso.confirmar(
                self.conexao, self.customer_id, proposta_id, self.limites
            )
        except pre_caso.Conflito:
            # Vencida ou situação mudou: reavalia a mesma transação com os fatos de agora.
            refeita = self._agir("contestar", transaction_id)
            aviso = texto("PROPOSTA-VENCIDA", self.idioma)
            return replace(refeita, textos=(aviso, *refeita.textos))
        return Saida(
            "POL-DISP-01",
            "registrar_pre_caso",
            (texto("PRE-CASO-REGISTRADO", self.idioma, protocolo=registrado.protocolo),),
            "livre",
            {"foco": transaction_id},
            transaction_id=transaction_id,
            protocolo=registrado.protocolo,
        )

    def _cortesia(self) -> Saida:
        """Responde com cordialidade sem mexer na etapa: a lista de opções, a transação em foco e a
        contagem de esclarecimentos continuam valendo. Na confirmação, o "gracias" sozinho não
        confirma nem cancela: a pergunta é repetida. A oferta de atendente sem etapa guardada
        (recusa sem motivo) é deixada, para um "sí" depois do "gracias" não encaminhar."""
        if self.estado == "confirmando":
            return self._confirmacao_pendente()
        estado, contexto = self.estado, self.contexto
        if estado == "oferecendo_humano":
            estado, contexto = "livre", _so_foco(contexto.get("foco"))
        clausula = "SAUDACAO" if self.lida.cortesia == "saudacao" else "AGRADECIMENTO"
        return Saida("CORTESIA", "responder", (texto(clausula, self.idioma),), estado, contexto)

    def _status_do_caso(self) -> Saida:
        """Pré-casos do cliente da sessão: o da transação em foco, se houver, senão todos."""
        self._fonte("app.pre_casos")
        casos = pre_caso.pre_casos_do_cliente(self.conexao, self.customer_id)
        em_foco = self.contexto.get("transaction_id") or self.contexto.get("foco")
        casos = [c for c in casos if c.transaction_id == em_foco] or casos
        decisao = politica.decidir_status_do_caso(len(casos))
        self._anotar("consultar_caso", decisao.regra)
        foco = _so_foco(self.contexto.get("foco"))
        if len(casos) == 1:
            resposta, t = self._caso(decisao.regra, casos[0])
            if t is None:  # a transação saiu da curada ou mudou de dono: não vira foco
                return Saida(decisao.regra, "responder", (resposta,), "livre", foco)
            return Saida(
                decisao.regra,
                "responder",
                (resposta,),
                "livre",
                {"foco": t.transaction_id},
                transaction_id=t.transaction_id,
            )
        extra = {}
        if casos:
            extra["casos"] = "\n".join(self._caso("CASO-ITEM", c)[0] for c in casos)
        resposta = texto(decisao.regra, self.idioma, **extra)
        return Saida(decisao.regra, "responder", (resposta,), "livre", foco)

    def _caso(
        self, clausula: str, caso: pre_caso.PreCaso
    ) -> tuple[str, TransacaoVerificada | None]:
        """Texto do pré-caso e a transação dele, esta só se ainda for do cliente na curada atual.
        O pré-caso sobrevive à recarga dos dados (PRD-002), mas a transação pode ter saído da
        curada ou mudado de dono: aí o texto cita só o registro (o identificador guardado no
        pré-caso), sem nenhum fato da curada de agora (ACH-037)."""
        t = self._do_cliente(caso.transaction_id)
        fatos = {
            "protocolo": caso.protocolo,
            "registro": f"{caso.criado_em:%d/%m/%Y}",
            "estado_caso": ESTADO_DO_CASO[caso.estado][self.idioma],
        }
        if t is None:
            fatos["transacao"] = caso.transaction_id
        return texto(clausula, self.idioma, t, **fatos), t

    def _cancelar(self) -> Saida:
        cancelado = texto("CANCELADO", self.idioma)
        return Saida(
            "CANCELADO", "responder", (cancelado,), "livre", _so_foco(self.contexto.get("foco"))
        )

    def _encaminhar(self, decisao: politica.Decisao, t: TransacaoVerificada | None) -> Saida:
        self._fonte("app.handoffs")
        pendencia = PENDENCIAS[decisao.regra]
        if decisao.detalhe:
            pendencia = f"{pendencia} ({decisao.detalhe})"
        atendimento = handoff.registrar(
            self.conexao,
            handoff.Encaminhamento(
                customer_id=self.customer_id,
                regra=decisao.regra,
                idioma=self.idioma,
                pedido=self.contexto.get("pedido") or self.mensagem,
                transacao=t,
                acoes=tuple(self.acoes),
                pendencias=(pendencia,),
            ),
        )
        clausula = CLAUSULA_DO_HUMANO.get(decisao.regra, decisao.regra)
        referencia = texto("ATENDIMENTO", self.idioma, atendimento=atendimento)
        return Saida(
            decisao.regra,
            "humano",
            (texto(clausula, self.idioma, t), referencia),
            "com_humano",
            {"atendimento": atendimento},
            transaction_id=None if t is None else t.transaction_id,
            atendimento=atendimento,
        )

    def _anotar(self, acao: str, resultado: str) -> None:
        self.acoes.append(handoff.Acao(acao, resultado))

    def _fonte(self, nome: str) -> None:
        self.fontes[nome] = None

    def _acoes_json(self) -> list[dict]:
        return [{"acao": a.acao, "resultado": a.resultado} for a in self.acoes]


def rastro_da_leitura(leitura: Leitura | None) -> dict:
    """Quem leu a mensagem e o uso do modelo (latência e tokens, se ele foi chamado), para o evento
    do turno ou do erro: toda chamada despachada fica contada, mesmo com o turno desfeito."""
    if leitura is None:
        return {}
    campos = {"interpretacao": leitura.fonte}
    if leitura.chamada is not None:
        campos |= {
            "modelo_latencia_ms": leitura.chamada.latencia_ms,
            "modelo_tokens_entrada": leitura.chamada.tokens_entrada,
            "modelo_tokens_saida": leitura.chamada.tokens_saida,
        }
    return campos


def _so_foco(foco: str | None) -> dict:
    return {} if foco is None else {"foco": foco}


def _pista_json(pista: politica.Pista) -> dict:
    return {
        "valor": None if pista.valor is None else str(pista.valor),
        "data": None if pista.data is None else pista.data.isoformat(),
        "comercio": pista.comercio,
        "ultima": pista.ultima,
    }


def _pista_do_contexto(guardada: dict | None) -> politica.Pista:
    if not guardada:
        return politica.Pista()
    valor, data = guardada.get("valor"), guardada.get("data")
    return politica.Pista(
        None if valor is None else Decimal(valor),
        None if data is None else date.fromisoformat(data),
        guardada.get("comercio"),
        guardada.get("ultima", False),
    )


def _somar(antes: politica.Pista, agora: politica.Pista) -> politica.Pista:
    """O que o cliente disse agora vale sobre o que disse antes, campo a campo."""
    return politica.Pista(
        agora.valor if agora.valor is not None else antes.valor,
        agora.data if agora.data is not None else antes.data,
        agora.comercio if agora.comercio is not None else antes.comercio,
        agora.ultima or antes.ultima,
    )


def _efeito(saida: Saida) -> str | None:
    """Efeito novo deste turno (o que foi criado), para o registro do turno."""
    if saida.acao == "registrar_pre_caso":
        return saida.protocolo
    if saida.acao == "humano":
        return saida.atendimento
    if saida.acao == "propor_pre_caso" and saida.proposta is not None:
        return saida.proposta.id
    return None


@dataclass(frozen=True)
class Preparo:
    """O que ler a mensagem precisa saber da conversa, lido sem travar nada."""

    idioma: Idioma
    estado: Estado
    hoje: date


def preparar(conexao: Connection, customer_id: str, conversa_id: str) -> Preparo:
    """Língua, estado e o "hoje" da leitura para ler a mensagem antes do turno: a leitura, que
    pode esperar o modelo, fica fora de qualquer transação e trava (ACH-030). O "hoje" é o relógio
    do banco, ou o último dia dos dados se a base carregada for mais antiga que ele (retrato)."""
    linha = _do_dono(conexao, customer_id, conversa_id, "idioma, estado")
    return Preparo(linha.idioma, linha.estado, consultas.hoje_dos_dados(conexao))


def ler(preparo: Preparo, mensagem: str, interpretador: Interpretador) -> Leitura:
    """A leitura da mensagem pelo interpretador configurado (regras ou cascata com o modelo).
    Em estado onde a leitura não decide nada, bastam as regras (língua da resposta): o modelo não
    é chamado."""
    if preparo.estado in TERMINAIS:
        return pelas_regras(mensagem, preparo.idioma, preparo.hoje)
    return interpretador(mensagem, preparo.idioma, preparo.hoje)


def turno(
    conexao: Connection,
    customer_id: str,
    conversa_id: str,
    mensagem: str,
    leitura: Leitura,
    limites: politica.Limites,
    ttl_minutos: int,
    inicio: float,
) -> ResultadoDoTurno:
    """Processa uma mensagem já lida do cliente da sessão na conversa dele e grava o turno e o
    evento. O interpretador só leu a mensagem; o que fazer é sempre a política que decide.
    `inicio` (time.perf_counter) vem de antes da leitura: a latência do turno inclui o modelo."""
    linha = _do_dono(conexao, customer_id, conversa_id, "estado, contexto, turnos", True)
    lida = leitura.lida
    atual = _Turno(
        conexao,
        customer_id,
        linha.estado,
        dict(linha.contexto),
        lida,
        mensagem,
        limites,
        ttl_minutos,
    )
    saida = atual.executar()
    numero = linha.turnos + 1
    resultado = ResultadoDoTurno(conversa_id, numero, lida.idioma, lida.intencao, saida)
    conexao.execute(
        text(
            "UPDATE app.conversas SET idioma = :idioma, estado = :estado,"
            " contexto = CAST(:contexto AS jsonb), turnos = :numero, atualizada_em = now()"
            " WHERE id = :id"
        ),
        {
            "id": conversa_id,
            "idioma": lida.idioma,
            "estado": saida.estado,
            "contexto": json.dumps(saida.contexto),
            "numero": numero,
        },
    )
    conexao.execute(
        text(
            "INSERT INTO app.turnos (conversa_id, numero, mensagem, idioma, intencao, regra, acao,"
            " estado, resposta, transaction_id, efeito) VALUES (:conversa, :numero, :mensagem,"
            " :idioma, :intencao, :regra, :acao, :estado, :resposta, :transacao, :efeito)"
        ),
        {
            "conversa": conversa_id,
            "numero": numero,
            "mensagem": mensagem[:LIMITE_MENSAGEM],
            "idioma": lida.idioma,
            "intencao": lida.intencao,
            "regra": saida.regra,
            "acao": saida.acao,
            "estado": saida.estado,
            "resposta": resultado.resposta,
            "transacao": saida.transaction_id,
            "efeito": _efeito(saida),
        },
    )
    eventos.registrar(
        conexao,
        eventos.Evento(
            tipo="turno",
            latencia_ms=eventos.desde(inicio),
            conversa_id=conversa_id,
            numero=numero,
            intencao=lida.intencao,
            regra=saida.regra,
            acao=saida.acao,
            efeito=_efeito(saida),
            fontes=tuple(atual.fontes),
            **rastro_da_leitura(leitura),
        ),
    )
    return resultado


def historico(conexao: Connection, customer_id: str, conversa_id: str) -> tuple[dict, list[dict]]:
    """Conversa e turnos, só para o dono (para reabrir a conversa depois de recarregar a página)."""
    conversa = _do_dono(conexao, customer_id, conversa_id, "id, idioma, estado")
    turnos = conexao.execute(
        text(
            "SELECT numero, mensagem, resposta, regra, acao, estado, criado_em FROM app.turnos"
            " WHERE conversa_id = :id ORDER BY numero"
        ),
        {"id": conversa_id},
    ).mappings()
    return dict(conversa._mapping), [dict(t) for t in turnos]
