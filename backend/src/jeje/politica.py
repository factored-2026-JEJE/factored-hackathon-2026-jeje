"""Política determinística do atendimento (DEV-010): regras com ID, fora de qualquer modelo.

Decide o que o sistema pode fazer diante de uma transação **do próprio cliente**, só com fatos
verificados da camada curada. Nenhum texto de conversa altera permissão: a interpretação (G10)
só escolhe qual pergunta fazer à política. Política **simulada e rotulada** — matriz de autonomia
no backlog (DEV-006), não política do banco. IDs `POL-*` aparecem no trace de cada decisão.
"""

import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, get_args

from jeje.mensagens import Status

Acao = Literal["responder", "esclarecer", "propor_pre_caso", "humano", "oferecer_humano", "recusar"]

# Códigos de recusa com explicação aprovada (95% das recusas da base; DEV-005).
CODIGOS_CATALOGADOS = frozenset({"05", "14", "51", "54"})
STATUS_CONHECIDOS = frozenset(get_args(Status))


@dataclass(frozen=True)
class Decisao:
    regra: str  # ID da regra aplicada (POL-*), sempre registrado
    acao: Acao
    detalhe: str | None = None


@dataclass(frozen=True)
class Fatos:
    """Fatos verificados de uma transação do cliente da sessão (nunca vindos do chat)."""

    transaction_id: str
    status: str
    response_code: str | None
    amount_usd: Decimal | None  # None quando não há conversão confiável (ACH-019)
    transaction_type: str | None = None
    channel: str | None = None
    transaction_date: datetime | None = None  # horário local da transação


@dataclass(frozen=True)
class Limites:
    """Limites da política simulada do banco (PRD-001, decididos por Jader), em USD, do compose."""

    padrao_usd: Decimal  # POL-HUM-02: por transação
    noturno_usd: Decimal  # POL-HUM-04: por transação noturna em canal digital
    noturno_dia_usd: Decimal  # POL-HUM-04: soma do dia das noturnas digitais já registradas
    noturno_inicio_h: int  # começo do período noturno (inclusive)
    noturno_fim_h: int  # fim do período noturno (exclusive)
    canais_digitais: frozenset[str]  # celular e computador
    seguranca_transferencia_usd: Decimal  # POL-SEG-01
    janela_contestacao_dias: int  # POL-HUM-05: idade máxima da compra, a partir do "hoje" dos dados
    reincidencia_pre_casos: int  # POL-HUM-06: pré-casos recentes do cliente que mandam para humano
    reincidencia_dias: int  # POL-HUM-06: o que conta como recente, no relógio real


def noturna_digital(fatos: Fatos, limites: Limites) -> bool:
    """Feita à noite por celular ou computador. A base não diz se o dispositivo é cadastrado:
    todo acesso digital noturno conta como não cadastrado (PRD-001, conservador)."""
    if fatos.transaction_date is None or fatos.channel not in limites.canais_digitais:
        return False
    hora, inicio, fim = fatos.transaction_date.hour, limites.noturno_inicio_h, limites.noturno_fim_h
    if inicio > fim:  # atravessa a meia-noite (ex.: das 20h às 6h)
        return hora >= inicio or hora < fim
    return inicio <= hora < fim


def transferencia_atipica(fatos: Fatos, limites: Limites) -> bool:
    """Transferência acima do limite de segurança: vai para análise (consulta ou contestação)."""
    return (
        fatos.transaction_type == "Transfer"
        and fatos.amount_usd is not None
        and fatos.amount_usd > limites.seguranca_transferencia_usd
    )


SEGURANCA = Decisao("POL-SEG-01", "humano", "transferência acima do limite de segurança")


def decidir_consulta(fatos: Fatos, limites: Limites) -> Decisao:
    """O que responder sobre a situação de uma transação."""
    if transferencia_atipica(fatos, limites):
        return SEGURANCA
    if fatos.status == "Approved":
        return Decisao("POL-CON-01", "responder")
    if fatos.status == "Declined":
        if fatos.response_code in CODIGOS_CATALOGADOS:
            return Decisao("POL-CON-03", "responder", fatos.response_code)
        # Sem código ou código fora do catálogo: informa o status sem inventar causa.
        return Decisao("POL-CON-04", "responder")
    if fatos.status in ("Pending", "Reversed"):
        return Decisao("POL-CON-05", "responder", fatos.status)
    return Decisao("POL-CON-04", "humano", "status desconhecido")


def idade_da_compra(fatos: Fatos, hoje: date | None) -> int | None:
    """Dias entre a compra e o "hoje" dos dados; sem uma das datas, desconhecida."""
    if hoje is None or fatos.transaction_date is None:
        return None
    return (hoje - fatos.transaction_date.date()).days


def decidir_contestacao(
    fatos: Fatos,
    limites: Limites,
    protocolo_existente: str | None,
    noturno_no_dia_usd: Decimal = Decimal("0"),
    hoje: date | None = None,
    pre_casos_recentes: int = 0,
) -> Decisao:
    """Pedido de contestação: pré-caso só para Approved do cliente, dentro dos limites simulados.
    `noturno_no_dia_usd` é o que o assistente já registrou hoje de noturnas digitais do cliente;
    `hoje` é o "hoje" dos dados (janela, POL-HUM-05) e `pre_casos_recentes` conta os pré-casos do
    cliente na janela de reincidência (POL-HUM-06)."""
    if protocolo_existente is not None:
        return Decisao("POL-DISP-03", "responder", protocolo_existente)
    if transferencia_atipica(fatos, limites):
        return SEGURANCA
    if fatos.status != "Approved":
        return Decisao("POL-DISP-02", "humano", fatos.status)
    idade = idade_da_compra(fatos, hoje)
    if idade is not None and idade > limites.janela_contestacao_dias:
        return Decisao("POL-HUM-05", "humano", f"compra de {idade} dias")
    if pre_casos_recentes >= limites.reincidencia_pre_casos:
        return Decisao("POL-HUM-06", "humano", f"{pre_casos_recentes} pré-casos recentes")
    if fatos.amount_usd is None:
        return Decisao("POL-HUM-02", "humano", "valor em USD indisponível")
    if noturna_digital(fatos, limites):
        if fatos.amount_usd > limites.noturno_usd:
            return Decisao("POL-HUM-04", "humano", "noturna digital acima do limite por transação")
        if noturno_no_dia_usd + fatos.amount_usd > limites.noturno_dia_usd:
            return Decisao("POL-HUM-04", "humano", "noturna digital acima do limite do dia")
    if fatos.amount_usd > limites.padrao_usd:
        return Decisao("POL-HUM-02", "humano", "acima do limite simulado")
    return Decisao("POL-DISP-01", "propor_pre_caso")


def decidir_status_do_caso(quantos: int) -> Decisao:
    """Status do pedido de revisão: só os pré-casos do cliente da sessão, relidos do banco. O
    assistente informa o registro e o estado; não tem prazo nem resultado da revisão."""
    if quantos == 0:
        return Decisao("POL-CASO-03", "responder", "nenhum pré-caso do cliente")
    return Decisao("POL-CASO-01" if quantos == 1 else "POL-CASO-02", "responder")


# ---- Pedido na conversa (POL-HUM-01/03, POL-ESC-01, POL-ID-02) ---------------------------------

ESCLARECIMENTOS_ATE_HUMANO = 2  # POL-HUM-03: perguntas de esclarecimento sem sucesso


def decidir_pedido(intencao: str, id_digitado: bool) -> Decisao | None:
    """Regras que valem antes de olhar qualquer transação; None → segue para consulta ou
    contestação. Segurança primeiro: relato de fraude vai para humano mesmo no meio de outro
    assunto, e identificador digitado no chat nunca vira busca."""
    if intencao == "fraude":
        return Decisao("POL-HUM-01", "humano", "relato de fraude")
    if intencao == "humano":
        return Decisao("POL-HUM-03", "humano", "pedido explícito")
    if intencao == "fora_de_escopo":
        return Decisao("POL-ESC-01", "recusar")
    if id_digitado:
        return Decisao("POL-ID-02", "recusar", "identificador digitado")
    return None


def decidir_esclarecimento(ja_feitos: int) -> Decisao:
    """Transação ou pedido não identificado: pergunta de novo até o limite; depois, oferece o
    atendente (encaminha só com o sim: quem não quer atendente segue na conversa)."""
    if ja_feitos >= ESCLARECIMENTOS_ATE_HUMANO:
        return Decisao("POL-HUM-03", "oferecer_humano", "esclarecimentos sem sucesso")
    return Decisao("POL-CON-02", "esclarecer")


# ---- Desambiguação (POL-CON-02) ----------------------------------------------------------------


@dataclass(frozen=True)
class Pista:
    """O que o cliente disse sobre a transação (extraído na interpretação)."""

    valor: Decimal | None = None
    data: date | None = None
    comercio: str | None = None
    ultima: bool = False  # "la última": das que casarem, a mais recente (critério do cliente)


@dataclass(frozen=True)
class Candidata:
    transaction_id: str
    amount: Decimal
    transaction_date: datetime
    merchant_name: str | None


@dataclass(frozen=True)
class Resolucao:
    tipo: Literal["unica", "varias", "nenhuma"]
    transacoes: tuple[str, ...]  # IDs (no máximo `maximo_opcoes` em "varias")
    regra: str = "POL-CON-02"


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _casa(candidata: Candidata, pista: Pista) -> bool:
    if pista.valor is not None and abs(candidata.amount - pista.valor) > Decimal("0.01"):
        return False
    if pista.data is not None and candidata.transaction_date.date() != pista.data:
        return False
    if pista.comercio is not None:
        nome = _sem_acento(candidata.merchant_name or "")
        if _sem_acento(pista.comercio) not in nome:
            return False
    return True


def resolver_transacao(
    candidatas: list[Candidata], pista: Pista, maximo_opcoes: int = 5
) -> Resolucao:
    """Nunca escolhe entre várias: uma → segue; várias → pergunta; nenhuma → pede dados. O único
    critério de escolha é o do cliente ("a última"): as candidatas vêm mais recentes primeiro."""
    casadas = [c for c in candidatas if _casa(c, pista)]
    if pista.ultima and casadas:
        casadas = casadas[:1]
    if len(casadas) == 1:
        return Resolucao("unica", (casadas[0].transaction_id,))
    if not casadas:
        return Resolucao("nenhuma", ())
    return Resolucao("varias", tuple(c.transaction_id for c in casadas[:maximo_opcoes]))
