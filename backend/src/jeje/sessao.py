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

from jeje.bloqueio import CARTOES
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


def personas_com_dicas(conexao: Connection, dias: int) -> list[dict]:
    """As personas na ordem provisionada, com o que ajuda a escolher o caminho da demonstração
    (PRD-009): cartões ativos ainda sem bloqueio feito por aqui (fraude com vários cartões),
    transações recusadas (caminho ambíguo) e pré-casos nos últimos `dias`, os da reincidência
    (POL-HUM-06). Uma consulta por tabela, só para os clientes que são persona."""
    return [
        dict(linha)
        for linha in conexao.execute(
            text(
                "WITH p AS (SELECT customer_id, nome, ordem FROM app.personas),"
                " cartoes AS (SELECT pr.customer_id, count(*) AS n FROM curated.products pr"
                "  WHERE pr.customer_id IN (SELECT customer_id FROM p)"
                "  AND pr.product_type = ANY(:cartoes) AND pr.product_status = 'Active'"
                "  AND NOT EXISTS (SELECT 1 FROM app.bloqueios b WHERE b.customer_id ="
                "   pr.customer_id AND b.product_id = pr.product_id AND b.desfeito_em IS NULL)"
                "  GROUP BY pr.customer_id),"
                " recusadas AS (SELECT t.customer_id, count(*) AS n FROM curated.transactions t"
                "  WHERE t.customer_id IN (SELECT customer_id FROM p)"
                "  AND t.transaction_status = 'Declined' GROUP BY t.customer_id),"
                " recentes AS (SELECT c.customer_id, count(*) AS n FROM app.pre_casos c"
                "  WHERE c.customer_id IN (SELECT customer_id FROM p)"
                "  AND c.criado_em >= now() - make_interval(days => :dias) GROUP BY c.customer_id)"
                " SELECT p.customer_id, p.nome, coalesce(cartoes.n, 0) AS cartoes_bloqueaveis,"
                " coalesce(recusadas.n, 0) AS transacoes_recusadas,"
                " coalesce(recentes.n, 0) AS pre_casos_recentes"
                " FROM p LEFT JOIN cartoes USING (customer_id)"
                " LEFT JOIN recusadas USING (customer_id) LEFT JOIN recentes USING (customer_id)"
                " ORDER BY p.ordem"
            ),
            {"cartoes": list(CARTOES), "dias": dias},
        ).mappings()
    ]


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
