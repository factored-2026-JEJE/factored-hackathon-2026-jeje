"""Schema app: personas de demonstração e sessões de teste.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA app")
    op.create_table(
        "personas",
        sa.Column("customer_id", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("ordem", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("customer_id", name="pk_personas"),
        sa.UniqueConstraint("ordem", name="uq_personas_ordem"),
        schema="app",
    )
    op.create_table(
        "sessoes",
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.Text(), nullable=False),
        sa.Column(
            "criada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token_hash", name="pk_sessoes"),
        schema="app",
    )
    op.create_index("ix_app_sessoes_customer_id", "sessoes", ["customer_id"], schema="app")


def downgrade() -> None:
    op.drop_index("ix_app_sessoes_customer_id", table_name="sessoes", schema="app")
    op.drop_table("sessoes", schema="app")
    op.drop_table("personas", schema="app")
    op.execute("DROP SCHEMA app")
