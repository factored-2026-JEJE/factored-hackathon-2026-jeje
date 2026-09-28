"""Fixtures compartilhadas. Tudo roda contra o PostgreSQL real do compose de testes (db-test)."""

import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text
from sqlalchemy.engine import make_url

from jeje.api import create_app
from jeje.config import Settings
from jeje.db import create_db_engine

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def alembic_config(settings: Settings) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["settings"] = settings
    return config


@contextmanager
def conexao(settings: Settings) -> Iterator[Connection]:
    """Conexão em transação (commit ao sair) com engine descartado ao final: sem conexões órfãs."""
    engine = create_db_engine(settings)
    try:
        with engine.begin() as con:
            yield con
    finally:
        engine.dispose()


@contextmanager
def cliente(settings: Settings) -> Iterator[TestClient]:
    """Cliente HTTP da aplicação real, com lifespan (abre e fecha o pool do banco)."""
    with TestClient(create_app(settings.model_copy(update={"api_root_path": ""}))) as http:
        yield http


@contextmanager
def servidor_http(settings: Settings) -> Iterator[str]:
    """Uvicorn real numa porta efêmera, com lifespan; devolve a URL base."""
    app = create_app(settings.model_copy(update={"api_root_path": ""}))
    servidor = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
    )
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    limite = time.monotonic() + 10
    while not servidor.started:
        if time.monotonic() > limite or not thread.is_alive():
            raise RuntimeError("servidor de teste não iniciou")
        time.sleep(0.01)
    porta = servidor.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{porta}"
    finally:
        servidor.should_exit = True
        thread.join(timeout=10)


def registrar_dataset(settings: Settings, version: str, source: str) -> None:
    """Registra diretamente no banco uma versão de dataset carregada (estado de teste)."""
    with conexao(settings) as con:
        con.execute(
            text("insert into meta.dataset_version (id, version, source) values (1, :v, :s)"),
            {"v": version, "s": source},
        )


@pytest.fixture
def banco_limpo():
    """Banco vazio e exclusivo do teste, criado no db-test e removido ao final."""
    base = Settings()
    url = make_url(base.database_url)
    nome = f"t_{uuid.uuid4().hex[:12]}"
    admin = create_db_engine(base).execution_options(isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as con:
            con.execute(text(f'CREATE DATABASE "{nome}"'))
        url_teste = url.set(database=nome).render_as_string(hide_password=False)
        yield base.model_copy(update={"database_url": url_teste})
        with admin.connect() as con:
            con.execute(text(f'DROP DATABASE "{nome}" WITH (FORCE)'))
    finally:
        admin.dispose()


@pytest.fixture
def banco_migrado(banco_limpo):
    """Banco exclusivo já no schema mais recente (alembic upgrade head)."""
    command.upgrade(alembic_config(banco_limpo), "head")
    return banco_limpo
