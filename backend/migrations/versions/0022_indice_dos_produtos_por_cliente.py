"""Índice por cliente na curada dos produtos: o bloqueio de cartão (PRD-007) procura os cartões do
cliente da sessão a cada turno do caminho, e as dicas das personas (PRD-009) também. Sem ele, cada
consulta varria os 400 mil produtos dos dados reais (~30 ms em três núcleos com a tabela em memória;
segundos sem ela). Mesmo caso das transações (0013).

Revision ID: 0022
Revises: 0021
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_curated_products_customer_id", "products", ["customer_id"], schema="curated"
    )


def downgrade() -> None:
    op.drop_index("ix_curated_products_customer_id", table_name="products", schema="curated")
