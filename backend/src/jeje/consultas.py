"""Consultas tipadas sobre a camada curada, sempre filtradas pelo cliente da sessão (DEV-009/011).

Não existe função que consulte transação sem o `customer_id` do dono: o filtro faz parte da
assinatura. Transação de outro cliente e transação inexistente são indistinguíveis para quem
consulta (nenhum dado, erro ou tempo diferente revela a existência).
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import Connection, text

from jeje.politica import Candidata, Fatos


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


COLUNAS_DOS_FATOS = (
    "t.transaction_id, t.transaction_status, t.response_code, t.amount_usd, t.transaction_type,"
    " t.channel, t.transaction_date"
)


def _fatos(linha) -> Fatos:
    return Fatos(
        transaction_id=linha.transaction_id,
        status=linha.transaction_status,
        response_code=linha.response_code,
        amount_usd=linha.amount_usd,
        transaction_type=linha.transaction_type,
        channel=linha.channel,
        transaction_date=linha.transaction_date,
    )


def fatos_da_transacao(conexao: Connection, customer_id: str, transaction_id: str) -> Fatos | None:
    """Fatos verificados para a política; `amount_usd` vem normalizado da curada (N-USD) e fica
    None quando não há conversão confiável — nunca usa o valor em moeda local como dólar."""
    linha = conexao.execute(
        text(
            f"SELECT {COLUNAS_DOS_FATOS} FROM curated.transactions t"
            " WHERE t.customer_id = :cliente AND t.transaction_id = :transacao"
        ),
        {"cliente": customer_id, "transacao": transaction_id},
    ).first()
    return None if linha is None else _fatos(linha)


def fatos_dos_pre_casos_de_hoje(conexao: Connection, customer_id: str) -> list[Fatos]:
    """Transações do cliente com pré-caso registrado hoje (relógio do banco)."""
    linhas = conexao.execute(
        text(
            f"SELECT {COLUNAS_DOS_FATOS} FROM app.pre_casos p JOIN curated.transactions t"
            " ON t.customer_id = p.customer_id AND t.transaction_id = p.transaction_id"
            " WHERE p.customer_id = :cliente AND p.criado_em >= current_date"
        ),
        {"cliente": customer_id},
    )
    return [_fatos(linha) for linha in linhas]


def candidatas_do_cliente(
    conexao: Connection, customer_id: str, status: str | None
) -> list[Candidata]:
    """Transações do cliente (opcionalmente só de um status), mais recentes primeiro: é entre
    elas, e nunca entre as de outro cliente, que a conversa resolve de qual se fala."""
    linhas = conexao.execute(
        text(
            "SELECT transaction_id, amount, transaction_date, merchant_name"
            " FROM curated.transactions WHERE customer_id = :cliente"
            " AND (CAST(:status AS text) IS NULL OR transaction_status = :status)"
            " ORDER BY transaction_date DESC, transaction_id"
        ),
        {"cliente": customer_id, "status": status},
    )
    return [Candidata(**linha._mapping) for linha in linhas]


def comercios_do_cliente(conexao: Connection, customer_id: str) -> list[str]:
    return list(
        conexao.execute(
            text(
                "SELECT DISTINCT merchant_name FROM curated.transactions"
                " WHERE customer_id = :cliente AND merchant_name IS NOT NULL ORDER BY 1"
            ),
            {"cliente": customer_id},
        ).scalars()
    )
