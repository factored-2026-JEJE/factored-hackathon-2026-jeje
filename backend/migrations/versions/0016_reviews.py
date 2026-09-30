"""Reviews das conversas de teste: quem do time avaliou, nota, se resolveu e o comentário, ligadas
à conversa (e por ela aos turnos), e a Issue do GitHub criada para cada uma, quando houver.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("conversa_id", sa.Text(), nullable=False),
        sa.Column("avaliador", sa.Text(), nullable=False),
        sa.Column("nota", sa.SmallInteger(), nullable=False),
        sa.Column("resolveu", sa.Text(), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=False),
        sa.Column("issue_url", sa.Text(), nullable=True),
        sa.Column(
            "criada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("nota BETWEEN 1 AND 5", name=op.f("ck_reviews_nota")),
        sa.CheckConstraint(
            "resolveu IN ('sim', 'parcial', 'nao')", name=op.f("ck_reviews_resolveu")
        ),
        sa.ForeignKeyConstraint(
            ["conversa_id"],
            ["app.conversas.id"],
            name=op.f("fk_reviews_conversa_id_conversas"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reviews")),
        schema="app",
    )
    op.create_index(op.f("ix_app_reviews_conversa_id"), "reviews", ["conversa_id"], schema="app")


def downgrade() -> None:
    op.drop_index(op.f("ix_app_reviews_conversa_id"), table_name="reviews", schema="app")
    op.drop_table("reviews", schema="app")
