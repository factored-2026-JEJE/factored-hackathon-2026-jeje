"""Acesso ao PostgreSQL: um engine por processo, criado a partir da configuração."""

from sqlalchemy import Engine, create_engine

from jeje.config import Settings


def create_db_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.db_connect_timeout_s},
    )
