"""Conversa sem modelo (G10): um turno = interpretar → política → ação verificada → resposta.

O estado da conversa fica no banco, travado durante o turno, sempre de um cliente da sessão; a
leitura da mensagem, que pode esperar o modelo, vem antes e fora da transação (ACH-030).
Nenhum turno pula a política: o texto só escolhe a pergunta feita a ela, e a transação só vem de
consulta filtrada pelo dono. Efeito (pré-caso) só com confirmação explícita ligada à proposta
guardada no estado; encaminhamento humano grava o resumo e encerra a automação da conversa.
Falha ao gravar propaga: quem chama desfaz o turno inteiro, sem resposta de sucesso.
"""

import json
import secrets
from dataclasses import dataclass, field, replace
from datetime import date
from functools import cached_property
from typing import Literal

from sqlalchemy import Connection, text

from jeje import consultas, eventos, handoff, politica, pre_caso
from jeje.interpretacao import Interpretacao, comercio_citado
from jeje.interpretacao_modelo import Interpretador, Leitura, pelas_regras
from jeje.mensagens import (
    ESTADO,
    MOTIVO_DO_CODIGO,
    Idioma,
    TransacaoVerificada,
    compor,
    descrever,
    marcadores,
)

Estado = Literal["livre", "esclarecendo", "confirmando", "oferecendo_humano", "com_humano"]
# Estados em que a automação não responde mais ao pedido (só lembra quem está com o caso).
SEM_LEITURA_DO_MODELO: frozenset[Estado] = frozenset({"com_humano"})

LIMITE_MENSAGEM = 500
MAXIMO_OPCOES = 5

# O que fica para o atendente resolver, por regra que encaminhou (texto interno, em português).
PENDENCIAS = {
    "POL-HUM-01": "Tratar relato de fraude: bloqueio e análise do cartão",
    "POL-HUM-02": "Revisar contestação que a automação não pode registrar",
    "POL-HUM-04": "Revisar contestação de transação noturna por celular ou computador",
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
            self._anotar("interpretar", f"{decisao.regra}: {', '.join(self.lida.sinais)}")
            return self._encaminhar(decisao, self._em_foco())
        if self.estado == "confirmando" and self.lida.resposta is not None:
            return self._confirmar() if self.lida.resposta == "sim" else self._cancelar()
        if self.estado == "oferecendo_humano" and self.lida.resposta is not None:
            if self.lida.resposta == "nao":
                return self._cancelar()
            aceito = politica.Decisao("POL-HUM-03", "humano", "aceitou o atendente oferecido")
            return self._encaminhar(aceito, self._em_foco())
        if decisao is not None:
            # Recusa (fora de escopo, ID digitado) não desfaz o que estava pendente.
            recusa = texto(decisao.regra, self.idioma)
            return Saida(decisao.regra, "recusar", (recusa,), self.estado, self.contexto)
        if self.estado == "esclarecendo" and (escolhida := self._escolhida()) is not None:
            return self._agir(self.contexto["intencao"], escolhida)
        if self.lida.intencao in ("consultar", "contestar"):
            return self._pedido(self.lida.intencao)
        if self.estado in ("esclarecendo", "confirmando") and self._tem_pista():
            return self._resolver(self.contexto.get("intencao", "contestar"), novo_assunto=False)
        if self.estado == "esclarecendo":
            return self._perguntar(self.contexto["intencao"], None)
        if self.estado == "confirmando":
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
        if self._tem_pista():
            return self._pedido("consultar")
        return self._nao_entendido()

    def _nao_entendido(self) -> Saida:
        """Mensagem não entendida também é esclarecimento (POL-HUM-03): pede de novo até o limite
        e depois encaminha, com a primeira mensagem da sequência no resumo. Pedido entendido zera
        a contagem (o contexto é trocado)."""
        pedidos_de_novo = self.contexto.get("esclarecimentos", 0)
        decisao = politica.decidir_esclarecimento(pedidos_de_novo)
        if decisao.acao == "humano":
            self._anotar("esclarecer", f"{pedidos_de_novo} mensagens seguidas não entendidas")
            return self._encaminhar(decisao, self._em_foco())
        contexto = {
            **_so_foco(self.contexto.get("foco")),
            "pedido": self.contexto.get("pedido", self.mensagem[:280]),
            "esclarecimentos": pedidos_de_novo + 1,
        }
        return Saida("AJUDA", "esclarecer", (texto("AJUDA", self.idioma),), "livre", contexto)

    # ---- resolução da transação --------------------------------------------------------------

    def _tem_pista(self) -> bool:
        lida = self.lida
        pistas = (lida.valor, lida.data, lida.status, self._comercio)
        return any(p is not None for p in pistas)

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
        pista = politica.Pista(self.lida.valor, self.lida.data, self._comercio)
        resolucao = politica.resolver_transacao(self._candidatas(status), pista, MAXIMO_OPCOES)
        if resolucao.tipo == "unica":
            return self._agir(intencao, resolucao.transacoes[0])
        return self._perguntar(intencao, resolucao.transacoes)

    def _perguntar(self, intencao: str, opcoes_ids: tuple[str, ...] | None) -> Saida:
        """Pergunta qual transação (ou pede dados, se nenhuma casou); `None` repete as opções já
        apresentadas. Passado o limite de esclarecimentos, encaminha (POL-HUM-03)."""
        feitos = self.contexto.get("esclarecimentos", 0)
        decisao = politica.decidir_esclarecimento(feitos)
        if decisao.acao == "humano":
            self._anotar("esclarecer", f"{feitos} perguntas sem identificar a transação")
            return self._encaminhar(decisao, None)
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

    def _verificada(self, transaction_id: str) -> TransacaoVerificada:
        self._fonte("curated.transactions")
        t = consultas.transacao_do_cliente(self.conexao, self.customer_id, transaction_id)
        if t is None:  # só chegam aqui IDs lidos da curada para este cliente
            raise LookupError("transação do contexto não pertence ao cliente da sessão")
        return verificada(t)

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
    """Língua, estado e data de hoje (relógio do banco) para ler a mensagem antes do turno: a
    leitura, que pode esperar o modelo, fica fora de qualquer transação e trava (ACH-030)."""
    linha = _do_dono(conexao, customer_id, conversa_id, "idioma, estado, current_date AS hoje")
    return Preparo(linha.idioma, linha.estado, linha.hoje)


def ler(preparo: Preparo, mensagem: str, interpretador: Interpretador) -> Leitura:
    """A leitura da mensagem pelo interpretador configurado (regras ou cascata com o modelo).
    Em estado onde a leitura não decide nada, bastam as regras (língua da resposta): o modelo não
    é chamado."""
    if preparo.estado in SEM_LEITURA_DO_MODELO:
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
