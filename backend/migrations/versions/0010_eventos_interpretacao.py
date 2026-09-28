"""Quem leu a mensagem em cada turno: regras, modelo ou regras por fallback (G14).

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("eventos", sa.Column("interpretacao", sa.Text(), nullable=True), schema="app")


def downgrade() -> None:
    op.drop_column("eventos", "interpretacao", schema="app")
