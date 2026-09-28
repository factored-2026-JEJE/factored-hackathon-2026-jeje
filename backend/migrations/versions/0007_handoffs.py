"""Fila de encaminhamentos para humano (DEV-016).

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE app.handoff_seq")
    op.create_table(
        "handoffs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.Text(), nullable=False),
        sa.Column("regra", sa.Text(), nullable=False),
        sa.Column("idioma", sa.Text(), nullable=False),
        sa.Column("pedido", sa.Text(), nullable=False),
        sa.Column("transacao", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("acoes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("pendencias", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("estado", sa.Text(), server_default="aberto", nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_handoffs"),
        schema="app",
    )
    op.create_index("ix_app_handoffs_customer_id", "handoffs", ["customer_id"], schema="app")


def downgrade() -> None:
    op.drop_index("ix_app_handoffs_customer_id", table_name="handoffs", schema="app")
    op.drop_table("handoffs", schema="app")
    op.execute("DROP SEQUENCE app.handoff_seq")
