"""Eventos de atendimento para traces e métricas (G11).

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eventos",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("conversa_id", sa.Text(), nullable=True),
        sa.Column("numero", sa.Integer(), nullable=True),
        sa.Column("intencao", sa.Text(), nullable=True),
        sa.Column("regra", sa.Text(), nullable=True),
        sa.Column("acao", sa.Text(), nullable=True),
        sa.Column("efeito", sa.Text(), nullable=True),
        sa.Column(
            "fontes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("latencia_ms", sa.Numeric(12, 3), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("tipo IN ('turno', 'erro')", name="ck_eventos_tipo"),
        sa.CheckConstraint("latencia_ms >= 0", name="ck_eventos_latencia"),
        sa.PrimaryKeyConstraint("id", name="pk_eventos"),
        schema="app",
    )


def downgrade() -> None:
    op.drop_table("eventos", schema="app")
