"""Consultas tipadas sobre a camada curada, sempre filtradas pelo cliente da sessão (DEV-009/011).

Não existe função que consulte transação sem o `customer_id` do dono: o filtro faz parte da
assinatura. Transação de outro cliente e transação inexistente são indistinguíveis para quem
consulta (nenhum dado, erro ou tempo diferente revela a existência).
"""

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, WithJsonSchema
from sqlalchemy import Connection, text

from jeje.politica import Candidata, Fatos

# A base não informa o fuso: a data e a hora são as locais da transação e saem sem deslocamento.
# O contrato declara isso, e não `date-time`, que promete o deslocamento (RFC 3339, ACH-113).
DataHoraLocal = Annotated[
    datetime,
    WithJsonSchema(
        {
            "type": "string",
            "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$",
            "description": "Data e hora locais da transação, sem fuso (a base não informa o fuso)",
        }
    ),
]


class Transacao(BaseModel):
    transaction_id: str
    transaction_date: DataHoraLocal
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


def aprovadas_desde(
    conexao: Connection, clientes: Sequence[str], desde: date
) -> list[tuple[str, Decimal, str, Fatos]]:
    """As aprovadas dos clientes desde o dia, mais recentes primeiro: (cliente, valor e moeda como
    o cliente vê, fatos para a política). É de onde sai o exemplo de contestação das personas."""
    linhas = conexao.execute(
        text(
            f"SELECT t.customer_id, t.amount, t.currency, {COLUNAS_DOS_FATOS}"
            " FROM curated.transactions t WHERE t.customer_id = ANY(:clientes)"
            " AND t.transaction_status = 'Approved' AND t.transaction_date >= :desde"
            " ORDER BY t.customer_id, t.transaction_date DESC, t.transaction_id"
        ),
        {"clientes": list(clientes), "desde": desde},
    )
    return [(linha.customer_id, linha.amount, linha.currency, _fatos(linha)) for linha in linhas]


def valor_e_dia_repetidos(conexao: Connection, clientes: Sequence[str]) -> set[tuple]:
    """(cliente, valor, dia) de mais de uma transação do cliente: a frase com esse valor e esse dia
    não aponta uma só."""
    linhas = conexao.execute(
        text(
            "SELECT customer_id, amount, transaction_date::date FROM curated.transactions"
            " WHERE customer_id = ANY(:clientes) GROUP BY 1, 2, 3 HAVING count(*) > 1"
        ),
        {"clientes": list(clientes)},
    )
    return {tuple(linha) for linha in linhas}


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


# (banco, versão dos dados) → último dia com transação: a varredura roda uma vez por carga.
_DIA_DOS_DADOS: dict[tuple[str | None, str], date | None] = {}


def hoje_dos_dados(conexao: Connection) -> date:
    """O "hoje" da base: o relógio do banco, ou o último dia dos dados se a base carregada for mais
    antiga que ele (retrato). Lê as datas sem ano da conversa e conta a janela de contestação."""
    agora = conexao.execute(text("SELECT current_date")).scalar_one()
    dia = dia_dos_dados(conexao)
    return agora if dia is None else min(agora, dia)


def pre_casos_recentes(conexao: Connection, customer_id: str, dias: int) -> int:
    """Pré-casos do cliente registrados nos últimos `dias` dias do relógio real (POL-HUM-06): o
    pré-caso é um evento de agora, não da base."""
    return conexao.execute(
        text(
            "SELECT count(*) FROM app.pre_casos WHERE customer_id = :cliente"
            " AND criado_em > now() - make_interval(days => :dias)"
        ),
        {"cliente": customer_id, "dias": dias},
    ).scalar_one()


def dia_dos_dados(conexao: Connection) -> date | None:
    """Último dia com transação na base carregada. A base é um retrato: "ayer" ou "11 de marzo"
    se leem a partir dele, não do relógio (a fixture é de março de 2025). Lido uma vez por versão
    dos dados (a recarga troca a versão); sem versão registrada, lido de novo a cada vez."""
    versao = conexao.execute(text("SELECT version FROM meta.dataset_version")).scalar()
    chave = (conexao.engine.url.database, versao)
    if versao is not None and chave in _DIA_DOS_DADOS:
        return _DIA_DOS_DADOS[chave]
    dia = conexao.execute(
        text("SELECT max(transaction_date)::date FROM curated.transactions")
    ).scalar()
    if versao is not None:
        _DIA_DOS_DADOS[chave] = dia
    return dia
