"""Estado 'encerrada' da conversa: a recarga dos dados encerra o atendimento em curso (DEV-020i).

Revision ID: 0012
Revises: 0011
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# Nome real no banco (a convenção de nomes duplicou o prefixo na 0008).
NOME = "ck_conversas_ck_conversas_estado"
ANTES = ("livre", "esclarecendo", "confirmando", "oferecendo_humano", "com_humano")
DEPOIS = (*ANTES, "encerrada")


def _estados(estados: tuple[str, ...]) -> str:
    return "estado IN (" + ", ".join(f"'{e}'" for e in estados) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f(NOME), "conversas", schema="app", type_="check")
    op.create_check_constraint(op.f(NOME), "conversas", _estados(DEPOIS), schema="app")


def downgrade() -> None:
    op.execute("UPDATE app.conversas SET estado = 'livre' WHERE estado = 'encerrada'")
    op.drop_constraint(op.f(NOME), "conversas", schema="app", type_="check")
    op.create_check_constraint(op.f(NOME), "conversas", _estados(ANTES), schema="app")
