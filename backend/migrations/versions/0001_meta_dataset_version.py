"""Schema meta e versão do dataset carregado.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA meta")
    op.create_table(
        "dataset_version",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "loaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_dataset_version_linha_unica"),
        sa.PrimaryKeyConstraint("id", name="pk_dataset_version"),
        schema="meta",
    )


def downgrade() -> None:
    op.drop_table("dataset_version", schema="meta")
    op.execute("DROP SCHEMA meta")
