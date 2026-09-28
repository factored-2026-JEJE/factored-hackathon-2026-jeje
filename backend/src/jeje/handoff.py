"""Encaminhamento estruturado para humano (DEV-016).

O atendente recebe o motivo (regra), a língua, o pedido do cliente (truncado: minimização), os
fatos verificados da transação, o que o sistema tentou e o que ficou pendente — não a conversa
inteira nem dados de outros clientes. A transação só entra se veio de consulta filtrada pelo dono.
"""

import json
from dataclasses import asdict, dataclass, field

from sqlalchemy import Connection, text

from jeje.mensagens import Idioma, TransacaoVerificada

LIMITE_PEDIDO = 280


@dataclass(frozen=True)
class Acao:
    acao: str
    resultado: str


@dataclass(frozen=True)
class Encaminhamento:
    customer_id: str
    regra: str
    idioma: Idioma
    pedido: str
    transacao: TransacaoVerificada | None = None
    acoes: tuple[Acao, ...] = ()
    pendencias: tuple[str, ...] = field(default=())


def _transacao_json(t: TransacaoVerificada | None) -> str | None:
    if t is None:
        return None
    return json.dumps(
        {
            "transaction_id": t.transaction_id,
            "data": t.transaction_date.isoformat(),
            "valor": str(t.amount),
            "moeda": t.currency,
            "comercio": t.merchant_name,
            "status": t.transaction_status,
        }
    )


def registrar(conexao: Connection, e: Encaminhamento) -> str:
    """Grava o encaminhamento aberto e devolve o identificador lido de volta (AT-########)."""
    pedido = e.pedido if len(e.pedido) <= LIMITE_PEDIDO else e.pedido[: LIMITE_PEDIDO - 1] + "…"
    return conexao.execute(
        text(
            "INSERT INTO app.handoffs (id, customer_id, regra, idioma, pedido, transacao, acoes,"
            " pendencias) VALUES ('AT-' || lpad(nextval('app.handoff_seq')::text, 8, '0'),"
            " :cliente, :regra, :idioma, :pedido, CAST(:transacao AS jsonb),"
            " CAST(:acoes AS jsonb), CAST(:pendencias AS jsonb)) RETURNING id"
        ),
        {
            "cliente": e.customer_id,
            "regra": e.regra,
            "idioma": e.idioma,
            "pedido": pedido,
            "transacao": _transacao_json(e.transacao),
            "acoes": json.dumps([asdict(a) for a in e.acoes]),
            "pendencias": json.dumps(list(e.pendencias)),
        },
    ).scalar_one()


def fila(conexao: Connection, limite: int) -> list[dict]:
    """Encaminhamentos abertos, mais antigos primeiro (ordem de atendimento)."""
    linhas = conexao.execute(
        text(
            "SELECT id, customer_id, regra, idioma, pedido, transacao, acoes, pendencias, estado,"
            " criado_em FROM app.handoffs WHERE estado = 'aberto'"
            " ORDER BY criado_em, id LIMIT :limite"
        ),
        {"limite": limite},
    ).mappings()
    return [dict(linha) for linha in linhas]
