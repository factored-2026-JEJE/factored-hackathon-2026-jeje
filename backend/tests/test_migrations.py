"""Migrations reais: reversíveis e fiéis às invariantes do schema."""

import pytest
from alembic import command
from conftest import alembic_config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from jeje.db import create_db_engine

SCHEMAS_DO_PRODUTO = ("meta",)


def tabelas_do_produto(settings) -> set[str]:
    with create_db_engine(settings).connect() as conexao:
        linhas = conexao.execute(
            text(
                "select table_schema || '.' || table_name from information_schema.tables "
                "where table_schema = any(:schemas)"
            ),
            {"schemas": list(SCHEMAS_DO_PRODUTO)},
        )
        return {linha[0] for linha in linhas}


def schemas_existentes(settings) -> set[str]:
    with create_db_engine(settings).connect() as conexao:
        linhas = conexao.execute(text("select schema_name from information_schema.schemata"))
        return {linha[0] for linha in linhas}


def test_upgrade_downgrade_upgrade_volta_ao_mesmo_schema(banco_limpo):
    config = alembic_config(banco_limpo)

    command.upgrade(config, "head")
    depois_do_upgrade = tabelas_do_produto(banco_limpo)
    assert "meta.dataset_version" in depois_do_upgrade

    command.downgrade(config, "base")
    assert tabelas_do_produto(banco_limpo) == set()
    assert "meta" not in schemas_existentes(banco_limpo)

    command.upgrade(config, "head")
    assert tabelas_do_produto(banco_limpo) == depois_do_upgrade


def test_dataset_version_aceita_uma_unica_linha(banco_migrado):
    inserir = text(
        "insert into meta.dataset_version (id, version, source) values (:id, :v, 'fixture')"
    )
    engine = create_db_engine(banco_migrado)
    with engine.begin() as conexao:
        conexao.execute(inserir, {"id": 1, "v": "v1"})
    with pytest.raises(IntegrityError), engine.begin() as conexao:
        conexao.execute(inserir, {"id": 2, "v": "v2"})
