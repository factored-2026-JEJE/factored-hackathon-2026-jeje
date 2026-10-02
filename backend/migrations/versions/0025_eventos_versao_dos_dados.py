"""A versão dos dados no evento (DEV-044): `meta.dataset_version` guarda só a atual; com ela no
evento, depois de uma recarga ainda se sabe de qual versão saiu a resposta de um turno antigo.

Revision ID: 0025
Revises: 0024
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("eventos", sa.Column("versao_dos_dados", sa.Text(), nullable=True), schema="app")


def downgrade() -> None:
    op.drop_column("eventos", "versao_dos_dados", schema="app")
