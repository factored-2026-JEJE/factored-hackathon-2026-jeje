"""Tipos de evento `acao` (efeito fora de um turno: rota direta, atendente) e `recarga`: todo
efeito deixa trace, não só os da conversa.

Revision ID: 0015
Revises: 0014
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

# Nome real no banco (a convenção de nomes duplicou o prefixo na 0009).
NOME = "ck_eventos_ck_eventos_tipo"
ANTES = ("turno", "erro")
DEPOIS = (*ANTES, "acao", "recarga")


def _tipos(tipos: tuple[str, ...]) -> str:
    return "tipo IN (" + ", ".join(f"'{t}'" for t in tipos) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f(NOME), "eventos", schema="app", type_="check")
    op.create_check_constraint(op.f(NOME), "eventos", _tipos(DEPOIS), schema="app")


def downgrade() -> None:
    op.execute("DELETE FROM app.eventos WHERE tipo IN ('acao', 'recarga')")
    op.drop_constraint(op.f(NOME), "eventos", schema="app", type_="check")
    op.create_check_constraint(op.f(NOME), "eventos", _tipos(ANTES), schema="app")
