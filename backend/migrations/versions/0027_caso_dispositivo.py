"""O dispositivo da sessão no caso do atendente (2.1c, PRD-007, simulação): o design mostra o
dispositivo entre os fatos do caso, e o atendente sabe se o cliente falou de um dispositivo
cadastrado sem abrir a conversa. Anulável: os casos de antes não guardaram o dispositivo.

Revision ID: 0027
Revises: 0026
"""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("handoffs", sa.Column("dispositivo", sa.Text(), nullable=True), schema="app")
    op.create_check_constraint(
        op.f("ck_handoffs_dispositivo"),
        "handoffs",
        "dispositivo IN ('cadastrado', 'novo')",
        schema="app",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_handoffs_dispositivo"), "handoffs", schema="app", type_="check")
    op.drop_column("handoffs", "dispositivo", schema="app")
