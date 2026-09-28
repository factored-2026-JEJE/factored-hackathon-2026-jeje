"""Propostas e pré-casos de contestação (DEV-012).

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "propostas_pre_caso",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.Text(), nullable=False),
        sa.Column("transaction_id", sa.Text(), nullable=False),
        sa.Column("fatos", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "criada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_propostas_pre_caso"),
        schema="app",
    )
    op.execute("CREATE SEQUENCE app.protocolo_seq")
    op.create_table(
        "pre_casos",
        sa.Column("protocolo", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.Text(), nullable=False),
        sa.Column("transaction_id", sa.Text(), nullable=False),
        sa.Column("proposta_id", sa.Text(), nullable=False),
        sa.Column("estado", sa.Text(), server_default="recebido", nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("protocolo", name="pk_pre_casos"),
        sa.UniqueConstraint("proposta_id", name="uq_pre_casos_proposta_id"),
        sa.UniqueConstraint("customer_id", "transaction_id", name="uq_pre_casos_transacao"),
        schema="app",
    )


def downgrade() -> None:
    op.drop_table("pre_casos", schema="app")
    op.execute("DROP SEQUENCE app.protocolo_seq")
    op.drop_table("propostas_pre_caso", schema="app")
