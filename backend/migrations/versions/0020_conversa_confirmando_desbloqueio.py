"""Estado 'confirmando_desbloqueio' da conversa: o cliente confirma com um sim explícito o
desbloqueio de um cartão que ele mesmo pediu para bloquear, dentro do prazo (PRD-007).

Revision ID: 0020
Revises: 0019
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

# Nome real no banco (a convenção de nomes duplicou o prefixo na 0008).
NOME = "ck_conversas_ck_conversas_estado"
ANTES = (
    "livre", "esclarecendo", "confirmando", "oferecendo_humano", "com_humano", "encerrada",
    "escolhendo_cartao",
)  # fmt: skip
DEPOIS = (*ANTES, "confirmando_desbloqueio")


def _estados(estados: tuple[str, ...]) -> str:
    return "estado IN (" + ", ".join(f"'{e}'" for e in estados) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f(NOME), "conversas", schema="app", type_="check")
    op.create_check_constraint(op.f(NOME), "conversas", _estados(DEPOIS), schema="app")


def downgrade() -> None:
    op.execute(
        "UPDATE app.conversas SET estado = 'livre', contexto = '{}'::jsonb"
        " WHERE estado = 'confirmando_desbloqueio'"
    )
    op.drop_constraint(op.f(NOME), "conversas", schema="app", type_="check")
    op.create_check_constraint(op.f(NOME), "conversas", _estados(ANTES), schema="app")
