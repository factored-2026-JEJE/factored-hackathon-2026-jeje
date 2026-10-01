"""A versão de dados recusada pela carga (ACH-112): com uma versão anterior no banco, a nova que o
contrato recusa não derruba o serviço; a anterior continua valendo, e a recusa (versão, motivo e
quando) fica ao lado dela para a prontidão e a página de status. A próxima carga boa a apaga.

Revision ID: 0024
Revises: 0023
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dataset_version", sa.Column("recusada_versao", sa.Text()), schema="meta")
    op.add_column("dataset_version", sa.Column("recusada_motivo", sa.Text()), schema="meta")
    op.add_column(
        "dataset_version",
        sa.Column("recusada_em", sa.DateTime(timezone=True)),
        schema="meta",
    )


def downgrade() -> None:
    op.drop_column("dataset_version", "recusada_em", schema="meta")
    op.drop_column("dataset_version", "recusada_motivo", schema="meta")
    op.drop_column("dataset_version", "recusada_versao", schema="meta")
