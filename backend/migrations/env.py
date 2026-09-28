"""Ambiente Alembic. A URL vem da configuração do processo (compose) ou, em testes, do chamador."""

from alembic import context

import jeje.dados.raw  # noqa: F401  (registra as tabelas raw no metadata)
from jeje.config import Settings
from jeje.db import create_db_engine
from jeje.models import Base

# Schemas do produto; o restante do banco (ex.: public) não é gerenciado aqui.
SCHEMAS = {"meta", "raw"}


def incluir(nome, tipo, pais) -> bool:
    """Filtro do autogenerate: só compara schemas do produto (o default chega como None)."""
    if tipo == "schema":
        return nome in SCHEMAS
    return True


def executar() -> None:
    settings = context.config.attributes.get("settings") or Settings()
    engine = create_db_engine(settings)
    try:
        with engine.connect() as conexao:
            context.configure(
                connection=conexao,
                target_metadata=Base.metadata,
                include_schemas=True,
                include_name=incluir,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


executar()
