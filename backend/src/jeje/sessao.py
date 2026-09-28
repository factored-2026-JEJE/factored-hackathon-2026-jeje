"""Sessão de teste confiável (DEV-008): personas provisionadas pelo servidor e sessões por token.

A identidade do cliente vem só da sessão aberta para uma persona provisionada; nada que chegue no
chat, na URL ou no corpo escolhe o cliente. O token é aleatório e só existe no navegador; o banco
guarda o sha256 dele e a validade.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, text


class PersonaDesconhecida(Exception):
    """O cliente pedido não é uma persona de demonstração provisionada."""


@dataclass(frozen=True)
class SessaoAtiva:
    customer_id: str


def provisionar_personas(conexao: Connection, quantidade: int) -> list[str]:
    """Refaz `app.personas`: clientes curados com mais variedade de status de transação (cobre os
    caminhos da demonstração), desempate pelo ID; mesma base → mesmas personas."""
    conexao.execute(text("DELETE FROM app.personas"))
    conexao.execute(
        text(
            "INSERT INTO app.personas (customer_id, nome, ordem)"
            " SELECT c.customer_id,"
            "        coalesce(nullif(trim(concat_ws(' ', c.first_name, c.last_name)), ''),"
            "                 c.customer_id),"
            "        row_number() OVER (ORDER BY t.variedade DESC, c.customer_id)"
            " FROM (SELECT customer_id, count(DISTINCT transaction_status) AS variedade"
            "       FROM curated.transactions GROUP BY customer_id) t"
            " JOIN curated.customers c USING (customer_id)"
            " ORDER BY t.variedade DESC, c.customer_id LIMIT :quantidade"
        ),
        {"quantidade": quantidade},
    )
    return list(
        conexao.execute(text("SELECT customer_id FROM app.personas ORDER BY ordem")).scalars()
    )


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def abrir(conexao: Connection, customer_id: str, ttl_minutos: int) -> tuple[str, datetime]:
    """Abre sessão para uma persona provisionada; devolve (token, expira_em)."""
    persona = conexao.execute(
        text("SELECT 1 FROM app.personas WHERE customer_id = :c"), {"c": customer_id}
    ).first()
    if persona is None:
        raise PersonaDesconhecida(customer_id)
    token = secrets.token_urlsafe(32)
    expira_em = conexao.execute(
        text(
            "INSERT INTO app.sessoes (token_hash, customer_id, expira_em)"
            " VALUES (:h, :c, now() + make_interval(mins => :ttl)) RETURNING expira_em"
        ),
        {"h": hash_token(token), "c": customer_id, "ttl": ttl_minutos},
    ).scalar_one()
    return token, expira_em


def validar(conexao: Connection, token: str) -> SessaoAtiva | None:
    """Sessão ativa do token, ou None: inexistente, adulterado ou expirado (relógio do banco)."""
    customer_id = conexao.execute(
        text("SELECT customer_id FROM app.sessoes WHERE token_hash = :h AND expira_em > now()"),
        {"h": hash_token(token)},
    ).scalar_one_or_none()
    return None if customer_id is None else SessaoAtiva(customer_id=customer_id)
