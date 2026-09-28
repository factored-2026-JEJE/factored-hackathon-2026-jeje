"""Fixtures compartilhadas. Tudo roda contra o PostgreSQL real do compose de testes (db-test)."""

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from jeje.config import Settings

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def alembic_config(settings: Settings) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["settings"] = settings
    return config


@pytest.fixture
def banco_limpo():
    """Banco vazio e exclusivo do teste, criado no db-test e removido ao final."""
    base = Settings()
    url = make_url(base.database_url)
    nome = f"t_{uuid.uuid4().hex[:12]}"
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conexao:
        conexao.execute(text(f'CREATE DATABASE "{nome}"'))
    url_teste = url.set(database=nome).render_as_string(hide_password=False)
    yield base.model_copy(update={"database_url": url_teste})
    with admin.connect() as conexao:
        conexao.execute(text(f'DROP DATABASE "{nome}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def banco_migrado(banco_limpo):
    """Banco exclusivo já no schema mais recente (alembic upgrade head)."""
    command.upgrade(alembic_config(banco_limpo), "head")
    return banco_limpo
