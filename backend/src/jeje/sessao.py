"""Sessão de teste confiável (DEV-008): personas provisionadas pelo servidor e sessões por token.

A identidade do cliente vem só da sessão aberta para uma persona provisionada; nada que chegue no
chat, na URL ou no corpo escolhe o cliente. O token é aleatório e só existe no navegador; o banco
guarda o sha256 dele e a validade.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import Connection, text

from jeje.models import DISPOSITIVOS


class PersonaDesconhecida(Exception):
    """O cliente pedido não é uma persona de demonstração provisionada."""


Dispositivo = Literal[DISPOSITIVOS]
PADRAO: Dispositivo = "novo"  # sem escolha no acesso, o lado conservador (PRD-001, PRD-007)


@dataclass(frozen=True)
class SessaoAtiva:
    customer_id: str
    dispositivo: Dispositivo = PADRAO


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
            # Pares distintos (cliente, status) antes de contar: agregação em hash, sem a ordenação
            # em disco do count(DISTINCT) nas 4,4 mi transações (7,4 s; 14 s com o índice → 1,8 s).
            " FROM (SELECT customer_id, count(*) AS variedade FROM"
            "       (SELECT DISTINCT customer_id, transaction_status FROM curated.transactions) d"
            "       GROUP BY customer_id) t"
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


def abrir(
    conexao: Connection, customer_id: str, ttl_minutos: int, dispositivo: Dispositivo = PADRAO
) -> tuple[str, datetime]:
    """Abre sessão para uma persona provisionada, com o dispositivo simulado escolhido no acesso
    (gravado pelo servidor; nada do chat o muda); devolve (token, expira_em)."""
    persona = conexao.execute(
        text("SELECT 1 FROM app.personas WHERE customer_id = :c"), {"c": customer_id}
    ).first()
    if persona is None:
        raise PersonaDesconhecida(customer_id)
    token = secrets.token_urlsafe(32)
    expira_em = conexao.execute(
        text(
            "INSERT INTO app.sessoes (token_hash, customer_id, expira_em, dispositivo)"
            " VALUES (:h, :c, now() + make_interval(mins => :ttl), :d) RETURNING expira_em"
        ),
        {"h": hash_token(token), "c": customer_id, "ttl": ttl_minutos, "d": dispositivo},
    ).scalar_one()
    return token, expira_em


def validar(conexao: Connection, token: str) -> SessaoAtiva | None:
    """Sessão ativa do token, ou None: inexistente, adulterado, expirado (relógio do banco) ou de
    quem deixou de ser persona (as personas são refeitas a cada carga dos dados)."""
    linha = conexao.execute(
        text(
            "SELECT s.customer_id, s.dispositivo FROM app.sessoes s"
            " JOIN app.personas p USING (customer_id)"
            " WHERE s.token_hash = :h AND s.expira_em > now()"
        ),
        {"h": hash_token(token)},
    ).first()
    if linha is None:
        return None
    return SessaoAtiva(customer_id=linha.customer_id, dispositivo=linha.dispositivo)
