"""Índice por cliente na curada das transações: o atendimento filtra toda consulta pelo cliente
da sessão, e sem ele cada consulta varria a tabela inteira (353 ms nos dados reais).

Revision ID: 0013
Revises: 0012
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_curated_transactions_customer_id", "transactions", ["customer_id"], schema="curated"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_curated_transactions_customer_id", table_name="transactions", schema="curated"
    )
