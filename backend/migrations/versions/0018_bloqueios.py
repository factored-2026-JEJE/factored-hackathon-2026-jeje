"""Bloqueio simulado de cartão (PRD-007): um bloqueio ativo por cartão do cliente, com a fotografia
do cartão (tipo e 4 últimos dígitos), o tipo (preventivo ou completo, pelo dispositivo da sessão), o
motivo (pedido ou roubo/perda), o prazo de reversão e quem desfez. Sem FK para a curada: a recarga
troca a curada, e o bloqueio fica como registro.

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE app.bloqueio_seq")
    op.create_table(
        "bloqueios",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.Text(), nullable=False),
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("produto", sa.Text(), nullable=False),
        sa.Column("ultimos4", sa.Text(), nullable=True),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("dispositivo", sa.Text(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("reversivel_ate", sa.DateTime(timezone=True), nullable=False),
        sa.Column("desfeito_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("desfeito_por", sa.Text(), nullable=True),
        sa.CheckConstraint("tipo IN ('preventivo', 'completo')", name=op.f("ck_bloqueios_tipo")),
        sa.CheckConstraint("motivo IN ('pedido', 'roubo_perda')", name=op.f("ck_bloqueios_motivo")),
        sa.CheckConstraint(
            "dispositivo IN ('cadastrado', 'novo')", name=op.f("ck_bloqueios_dispositivo")
        ),
        sa.CheckConstraint(
            "desfeito_por IN ('cliente', 'atendente')", name=op.f("ck_bloqueios_desfeito_por")
        ),
        sa.CheckConstraint(
            "(desfeito_em IS NULL) = (desfeito_por IS NULL)", name=op.f("ck_bloqueios_desfeito")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bloqueios")),
        schema="app",
    )
    op.create_index(
        "uq_bloqueios_ativo",
        "bloqueios",
        ["customer_id", "product_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("desfeito_em IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_bloqueios_ativo", table_name="bloqueios", schema="app")
    op.drop_table("bloqueios", schema="app")
    op.execute("DROP SEQUENCE app.bloqueio_seq")
