"""Id da requisição (X-Request-ID) no evento: liga a resposta, o log e o trace do banco.

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("eventos", sa.Column("requisicao", sa.Text(), nullable=True), schema="app")


def downgrade() -> None:
    op.drop_column("eventos", "requisicao", schema="app")
