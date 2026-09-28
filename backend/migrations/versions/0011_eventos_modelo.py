"""Contabilidade de cada chamada ao modelo no evento do turno: latência e tokens (DEV-015b).

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "eventos", sa.Column("modelo_latencia_ms", sa.Numeric(12, 3), nullable=True), schema="app"
    )
    op.add_column(
        "eventos", sa.Column("modelo_tokens_entrada", sa.Integer(), nullable=True), schema="app"
    )
    op.add_column(
        "eventos", sa.Column("modelo_tokens_saida", sa.Integer(), nullable=True), schema="app"
    )


def downgrade() -> None:
    op.drop_column("eventos", "modelo_tokens_saida", schema="app")
    op.drop_column("eventos", "modelo_tokens_entrada", schema="app")
    op.drop_column("eventos", "modelo_latencia_ms", schema="app")
