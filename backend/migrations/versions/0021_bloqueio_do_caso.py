"""Bloqueio ligado ao caso do atendente (PRD-009): o bloqueio que entra num caso de bloqueio (relato
de fraude, bloqueio preventivo ou pedido de desbloqueio) guarda o encaminhamento, para que todo
desbloqueio, pelo cliente em até 7 dias ou pelo atendente, seja anotado no caso. Anulável: bloqueio
pedido com dispositivo cadastrado não tem caso.

Revision ID: 0021
Revises: 0020
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bloqueios", sa.Column("atendimento", sa.Text(), nullable=True), schema="app")
    op.create_foreign_key(
        op.f("fk_bloqueios_atendimento_handoffs"),
        "bloqueios",
        "handoffs",
        ["atendimento"],
        ["id"],
        source_schema="app",
        referent_schema="app",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_bloqueios_atendimento_handoffs"), "bloqueios", schema="app", type_="foreignkey"
    )
    op.drop_column("bloqueios", "atendimento", schema="app")
