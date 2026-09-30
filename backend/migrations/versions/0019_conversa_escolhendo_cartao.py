"""Estado 'escolhendo_cartao' da conversa: o cliente diz qual cartão bloquear (PRD-007).

Revision ID: 0019
Revises: 0018
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

# Nome real no banco (a convenção de nomes duplicou o prefixo na 0008).
NOME = "ck_conversas_ck_conversas_estado"
ANTES = ("livre", "esclarecendo", "confirmando", "oferecendo_humano", "com_humano", "encerrada")
DEPOIS = (*ANTES, "escolhendo_cartao")


def _estados(estados: tuple[str, ...]) -> str:
    return "estado IN (" + ", ".join(f"'{e}'" for e in estados) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f(NOME), "conversas", schema="app", type_="check")
    op.create_check_constraint(op.f(NOME), "conversas", _estados(DEPOIS), schema="app")


def downgrade() -> None:
    op.execute(
        "UPDATE app.conversas SET estado = 'livre', contexto = '{}'::jsonb"
        " WHERE estado = 'escolhendo_cartao'"
    )
    op.drop_constraint(op.f(NOME), "conversas", schema="app", type_="check")
    op.create_check_constraint(op.f(NOME), "conversas", _estados(ANTES), schema="app")
