"""Consultas tipadas sobre a camada curada, sempre filtradas pelo cliente da sessão (DEV-009/011).

Não existe função que consulte transação sem o `customer_id` do dono: o filtro faz parte da
assinatura. Transação de outro cliente e transação inexistente são indistinguíveis para quem
consulta (nenhum dado, erro ou tempo diferente revela a existência).
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import Connection, text


class Transacao(BaseModel):
    transaction_id: str
    transaction_date: datetime
    amount: Decimal
    currency: str
    transaction_status: str
    response_code: str | None
    transaction_type: str | None
    merchant_name: str | None
    channel: str | None


COLUNAS = (
    "transaction_id, transaction_date, amount, currency, transaction_status, response_code,"
    " transaction_type, merchant_name, channel"
)


def transacoes_do_cliente(conexao: Connection, customer_id: str, limite: int) -> list[Transacao]:
    linhas = conexao.execute(
        text(
            f"SELECT {COLUNAS} FROM curated.transactions WHERE customer_id = :cliente"
            " ORDER BY transaction_date DESC, transaction_id LIMIT :limite"
        ),
        {"cliente": customer_id, "limite": limite},
    ).mappings()
    return [Transacao(**linha) for linha in linhas]


def transacao_do_cliente(
    conexao: Connection, customer_id: str, transaction_id: str
) -> Transacao | None:
    linha = (
        conexao.execute(
            text(
                f"SELECT {COLUNAS} FROM curated.transactions"
                " WHERE customer_id = :cliente AND transaction_id = :transacao"
            ),
            {"cliente": customer_id, "transacao": transaction_id},
        )
        .mappings()
        .first()
    )
    return None if linha is None else Transacao(**linha)
