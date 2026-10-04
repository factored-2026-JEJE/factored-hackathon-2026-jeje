"""Estado 'confirmando_bloqueio' da conversa: a pergunta hipotética ou de capacidade sobre bloquear
("¿cómo bloqueo la tarjeta si la pierdo?") espera um sim antes de bloquear (REG-20, POL-BLQ-07).

Revision ID: 0026
Revises: 0025
"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

# Nome real no banco (a convenção de nomes duplicou o prefixo na 0008).
NOME = "ck_conversas_ck_conversas_estado"
ANTES = (
    "livre", "esclarecendo", "confirmando", "oferecendo_humano", "com_humano", "encerrada",
    "escolhendo_cartao", "confirmando_desbloqueio",
)  # fmt: skip
DEPOIS = (*ANTES, "confirmando_bloqueio")


def _estados(estados: tuple[str, ...]) -> str:
    return "estado IN (" + ", ".join(f"'{e}'" for e in estados) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f(NOME), "conversas", schema="app", type_="check")
    op.create_check_constraint(op.f(NOME), "conversas", _estados(DEPOIS), schema="app")


def downgrade() -> None:
    op.execute(
        "UPDATE app.conversas SET estado = 'livre', contexto = '{}'::jsonb"
        " WHERE estado = 'confirmando_bloqueio'"
    )
    op.drop_constraint(op.f(NOME), "conversas", schema="app", type_="check")
    op.create_check_constraint(op.f(NOME), "conversas", _estados(ANTES), schema="app")
