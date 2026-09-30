"""Bloqueio simulado de cartão (PRD-007): só para cartão ativo do cliente da sessão, idempotente (um
bloqueio ativo por cartão) e relido antes de dizer que bloqueou. A curada não muda, porque é dado do
desafio e não existe sistema de cartões: o bloqueio fica em `app.bloqueios`, com a fotografia do
cartão (tipo e os 4 últimos dígitos; o número inteiro nunca sai da curada)."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, text

from jeje import politica

# Tipos de produto que são cartão na base do desafio.
CARTOES = ("Tarjeta Crédito", "Tarjeta Débito")
FONTES = ("curated.products", "app.bloqueios")
COLUNAS = (
    "id, customer_id, product_id, produto, ultimos4, tipo, motivo, dispositivo, criado_em,"
    " reversivel_ate, desfeito_em, desfeito_por"
)


class NaoBloqueavel(Exception):
    """O produto não é um cartão ativo do cliente da sessão."""


class NaoEncontrado(Exception):
    """Bloqueio inexistente."""


class JaDesfeito(Exception):
    """O bloqueio já foi desfeito."""


@dataclass(frozen=True)
class Bloqueio:
    id: str
    customer_id: str
    product_id: str
    produto: str
    ultimos4: str | None
    tipo: str
    motivo: str
    dispositivo: str
    criado_em: datetime
    reversivel_ate: datetime
    desfeito_em: datetime | None = None
    desfeito_por: str | None = None


def cartoes_do_cliente(conexao: Connection, customer_id: str) -> list[politica.Cartao]:
    """Os cartões do cliente da sessão, com o status da base e o bloqueio ativo do canal."""
    linhas = conexao.execute(
        text(
            "SELECT p.product_id, p.product_type AS produto,"
            " right(p.product_number, 4) AS ultimos4, p.product_status AS status, b.id AS bloqueio"
            " FROM curated.products p LEFT JOIN app.bloqueios b"
            " ON b.customer_id = p.customer_id AND b.product_id = p.product_id"
            " AND b.desfeito_em IS NULL"
            " WHERE p.customer_id = :cliente AND p.product_type = ANY(:cartoes)"
            " ORDER BY p.product_type, p.product_id"
        ),
        {"cliente": customer_id, "cartoes": list(CARTOES)},
    ).mappings()
    return [politica.Cartao(**linha) for linha in linhas]


def bloqueio_ativo(conexao: Connection, customer_id: str, product_id: str) -> Bloqueio | None:
    linha = conexao.execute(
        text(
            f"SELECT {COLUNAS} FROM app.bloqueios"
            " WHERE customer_id = :cliente AND product_id = :produto AND desfeito_em IS NULL"
        ),
        {"cliente": customer_id, "produto": product_id},
    ).one_or_none()
    return None if linha is None else Bloqueio(**linha._mapping)


def bloquear(
    conexao: Connection,
    customer_id: str,
    product_id: str,
    tipo: str,
    motivo: str,
    dispositivo: str,
    janela_dias: int,
) -> tuple[Bloqueio, bool]:
    """Devolve (bloqueio relido, criado_agora). Um bloqueio ativo por cartão: pedir de novo devolve
    o que já existe. Produto que não é cartão ativo do cliente: NaoBloqueavel. Gravação que não se
    confirma na releitura: RuntimeError, sem dizer que bloqueou."""
    cartao = conexao.execute(
        text(
            "SELECT product_type, right(product_number, 4) AS ultimos4 FROM curated.products"
            " WHERE customer_id = :cliente AND product_id = :produto"
            " AND product_type = ANY(:cartoes) AND product_status = 'Active'"
        ),
        {"cliente": customer_id, "produto": product_id, "cartoes": list(CARTOES)},
    ).first()
    if cartao is None:
        raise NaoBloqueavel(product_id)
    inserido = conexao.execute(
        text(
            "INSERT INTO app.bloqueios (id, customer_id, product_id, produto, ultimos4, tipo,"
            " motivo, dispositivo, reversivel_ate)"
            " VALUES ('BL-' || lpad(nextval('app.bloqueio_seq')::text, 8, '0'), :cliente,"
            " :produto, :tipo_do_produto, :ultimos4, :tipo, :motivo, :dispositivo,"
            " now() + make_interval(days => :janela))"
            " ON CONFLICT DO NOTHING"
        ),
        {
            "cliente": customer_id,
            "produto": product_id,
            "tipo_do_produto": cartao.product_type,
            "ultimos4": cartao.ultimos4,
            "tipo": tipo,
            "motivo": motivo,
            "dispositivo": dispositivo,
            "janela": janela_dias,
        },
    ).rowcount
    relido = bloqueio_ativo(conexao, customer_id, product_id)
    if relido is None:
        raise RuntimeError("bloqueio não encontrado na releitura; nada foi bloqueado")
    return relido, inserido == 1


def ativos(conexao: Connection, limite: int) -> list[Bloqueio]:
    """Bloqueios ativos, os mais recentes primeiro (console do atendente): com dispositivo
    cadastrado, o aviso ao atendente é o bloqueio aparecer ali (PRD-007)."""
    linhas = conexao.execute(
        text(
            f"SELECT {COLUNAS} FROM app.bloqueios WHERE desfeito_em IS NULL"
            " ORDER BY criado_em DESC, id DESC LIMIT :limite"
        ),
        {"limite": limite},
    )
    return [Bloqueio(**linha._mapping) for linha in linhas]


def desfazer(conexao: Connection, bloqueio_id: str, por: str) -> Bloqueio:
    """Desfaz o bloqueio ativo e devolve o registro como ficou; ninguém desfaz duas vezes.
    Inexistente: NaoEncontrado; já desfeito: JaDesfeito."""
    linha = conexao.execute(
        text(
            "UPDATE app.bloqueios SET desfeito_em = now(), desfeito_por = :por"
            f" WHERE id = :id AND desfeito_em IS NULL RETURNING {COLUNAS}"
        ),
        {"id": bloqueio_id, "por": por},
    ).first()
    if linha is not None:
        return Bloqueio(**linha._mapping)
    existe = conexao.execute(
        text("SELECT 1 FROM app.bloqueios WHERE id = :id"), {"id": bloqueio_id}
    ).first()
    raise JaDesfeito(bloqueio_id) if existe else NaoEncontrado(bloqueio_id)
