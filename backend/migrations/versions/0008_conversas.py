"""Conversas e turnos do atendimento sem modelo (G10).

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversas",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.Text(), nullable=False),
        sa.Column("idioma", sa.Text(), nullable=False),
        sa.Column("estado", sa.Text(), server_default="livre", nullable=False),
        sa.Column(
            "contexto",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("turnos", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "criada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "atualizada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("idioma IN ('es', 'pt')", name="ck_conversas_idioma"),
        sa.CheckConstraint(
            "estado IN ('livre', 'esclarecendo', 'confirmando', 'oferecendo_humano', 'com_humano')",
            name="ck_conversas_estado",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversas"),
        schema="app",
    )
    op.create_index("ix_app_conversas_customer_id", "conversas", ["customer_id"], schema="app")
    op.create_table(
        "turnos",
        sa.Column("conversa_id", sa.Text(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=False),
        sa.Column("idioma", sa.Text(), nullable=False),
        sa.Column("intencao", sa.Text(), nullable=False),
        sa.Column("regra", sa.Text(), nullable=False),
        sa.Column("acao", sa.Text(), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("resposta", sa.Text(), nullable=False),
        sa.Column("transaction_id", sa.Text(), nullable=True),
        sa.Column("efeito", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["conversa_id"], ["app.conversas.id"], name="fk_turnos_conversa_id_conversas"
        ),
        sa.PrimaryKeyConstraint("conversa_id", "numero", name="pk_turnos"),
        schema="app",
    )


def downgrade() -> None:
    op.drop_table("turnos", schema="app")
    op.drop_index("ix_app_conversas_customer_id", table_name="conversas", schema="app")
    op.drop_table("conversas", schema="app")
