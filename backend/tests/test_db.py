"""Engine contra o PostgreSQL real do compose de testes."""

import time

import pytest
from conftest import conexao
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from jeje.config import Settings


def test_engine_conecta_no_banco_de_teste_postgres_16():
    with conexao(Settings()) as con:
        banco = con.execute(text("select current_database()")).scalar_one()
        versao = int(con.execute(text("show server_version_num")).scalar_one())
    # Nome e versão vêm do compose de testes (db-test, postgres:16), não do código testado.
    assert banco == "jeje_test"
    assert 160000 <= versao < 170000


def test_banco_mudo_falha_dentro_do_timeout_configurado():
    # 192.0.2.1 (TEST-NET-1) não responde: sem timeout a conexão ficaria presa por minutos.
    settings = Settings(
        database_url="postgresql+psycopg://jeje:jeje@192.0.2.1:5432/nada",
        db_connect_timeout_s=1,
    )
    inicio = time.monotonic()
    with pytest.raises(OperationalError), conexao(settings):
        pass
    assert time.monotonic() - inicio < 5
