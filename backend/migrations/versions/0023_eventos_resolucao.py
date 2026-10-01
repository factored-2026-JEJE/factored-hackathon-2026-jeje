"""Como a transação do turno foi achada, no evento (DEV-071, ACH-118 da validação): o resolvedor
(filtro exato, ranking, escolha do cliente ou a transação em foco) e, pelo ranking, a versão da
calibração, a probabilidade da primeira e quantas podiam ser. É o registro de que a auditoria
precisa para separar o erro do ranking do erro do filtro, e o DEV-041 para recalibrar.

Revision ID: 0023
Revises: 0022
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("eventos", sa.Column("resolvedor", sa.Text(), nullable=True), schema="app")
    op.add_column("eventos", sa.Column("calibracao", sa.Text(), nullable=True), schema="app")
    op.add_column(
        "eventos", sa.Column("probabilidade", sa.Numeric(5, 4), nullable=True), schema="app"
    )
    op.add_column("eventos", sa.Column("possiveis", sa.Integer(), nullable=True), schema="app")
    # O mesmo CHECK do modelo (jeje.models.RESOLVEDORES), escrito à mão: a migration não importa o
    # código da aplicação, que pode mudar depois dela.
    op.create_check_constraint(
        "ck_eventos_resolvedor",
        "eventos",
        "resolvedor IN ('filtro', 'ranking', 'escolha', 'foco')",
        schema="app",
    )


def downgrade() -> None:
    op.drop_constraint("ck_eventos_resolvedor", "eventos", schema="app", type_="check")
    op.drop_column("eventos", "possiveis", schema="app")
    op.drop_column("eventos", "probabilidade", schema="app")
    op.drop_column("eventos", "calibracao", schema="app")
    op.drop_column("eventos", "resolvedor", schema="app")
