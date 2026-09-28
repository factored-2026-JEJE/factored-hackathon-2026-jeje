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
from typing import Literal

Acao = Literal["responder", "esclarecer", "propor_pre_caso", "humano", "recusar"]

# Códigos de recusa com explicação aprovada (95% das recusas da base; DEV-005).
CODIGOS_CATALOGADOS = frozenset({"05", "14", "51", "54"})
STATUS_CONHECIDOS = frozenset({"Approved", "Declined", "Pending", "Reversed"})


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


def decidir_consulta(fatos: Fatos) -> Decisao:
    """O que responder sobre a situação de uma transação."""
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


def decidir_contestacao(
    fatos: Fatos, limite_usd: Decimal, protocolo_existente: str | None
) -> Decisao:
    """Pedido de contestação: pré-caso só para Approved do cliente, dentro do limite simulado."""
    if protocolo_existente is not None:
        return Decisao("POL-DISP-03", "responder", protocolo_existente)
    if fatos.status != "Approved":
        return Decisao("POL-DISP-02", "humano", fatos.status)
    if fatos.amount_usd is None:
        return Decisao("POL-HUM-02", "humano", "valor em USD indisponível")
    if fatos.amount_usd > limite_usd:
        return Decisao("POL-HUM-02", "humano", "acima do limite simulado")
    return Decisao("POL-DISP-01", "propor_pre_caso")


# ---- Desambiguação (POL-CON-02) ----------------------------------------------------------------


@dataclass(frozen=True)
class Pista:
    """O que o cliente disse sobre a transação (extraído na interpretação)."""

    valor: Decimal | None = None
    data: date | None = None
    comercio: str | None = None


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
    """Nunca escolhe entre várias: uma → segue; várias → pergunta; nenhuma → pede dados."""
    casadas = [c for c in candidatas if _casa(c, pista)]
    if len(casadas) == 1:
        return Resolucao("unica", (casadas[0].transaction_id,))
    if not casadas:
        return Resolucao("nenhuma", ())
    return Resolucao("varias", tuple(c.transaction_id for c in casadas[:maximo_opcoes]))
