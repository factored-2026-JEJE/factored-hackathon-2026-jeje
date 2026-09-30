"""Dispositivo da sessão de teste (PRD-007, simulação): "cadastrado" ou "novo", escolhido no acesso
da demo e gravado pelo servidor; o chat não muda isso. Sem escolha, "novo" (conservador).

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessoes",
        sa.Column("dispositivo", sa.Text(), server_default="novo", nullable=False),
        schema="app",
    )
    op.create_check_constraint(
        op.f("ck_sessoes_dispositivo"),
        "sessoes",
        "dispositivo IN ('cadastrado', 'novo')",
        schema="app",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_sessoes_dispositivo"), "sessoes", schema="app", type_="check")
    op.drop_column("sessoes", "dispositivo", schema="app")
