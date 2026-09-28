"""Versão do pipeline de dados junto da versão do dataset.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dataset_version",
        sa.Column("pipeline", sa.Text(), server_default="", nullable=False),
        schema="meta",
    )


def downgrade() -> None:
    op.drop_column("dataset_version", "pipeline", schema="meta")
