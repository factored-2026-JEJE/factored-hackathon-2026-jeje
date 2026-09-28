"""Configuração e orquestração do pipeline de dados (o que o serviço seed executa)."""

import os

import pytest
from conftest import conexao
from pydantic import ValidationError
from sqlalchemy import text
from test_carga import escrever_csv
from test_download import cliente

from jeje.dados import manifesto
from jeje.dados.__main__ import main, preparar
from jeje.dados.config import ConfigDados

TABELAS = "complaints, branches"


@pytest.fixture
def ambiente_fixture(tmp_path, monkeypatch):
    raiz, manifestos = tmp_path / "raw", tmp_path / "manifesto"
    escrever_csv(raiz, "complaints/year=2025/month=03/day=10/c.csv", "complaints", [
        {"complaint_id": "CMP-1"}, {"complaint_id": "CMP-2"},
    ])  # fmt: skip
    escrever_csv(raiz, "branches.csv", "branches", [{"branch_id": "SUC-1"}])
    manifesto.escrever(manifestos, manifesto.gerar(raiz, ["complaints", "branches"]))
    for chave, valor in {
        "DATASET_RAW_DIR": str(raiz),
        "DATASET_MANIFEST_DIR": str(manifestos),
        "DATASET_TABLES": TABELAS,
        "DATASET_SOURCE": "fixture",
        "DATASET_S3_ENDPOINT": "",
        "DATASET_DOWNLOAD_WORKERS": "2",
    }.items():
        monkeypatch.setenv(chave, valor)
    monkeypatch.delenv("DATASET_S3_URI", raising=False)
    return raiz, manifestos


def contagens(settings) -> tuple[int, int, int]:
    with conexao(settings) as con:
        return tuple(
            con.execute(text(f"select count(*) from raw.{tabela}")).scalar_one()
            for tabela in ("complaints", "branches", "customers")
        )


def test_config_s3_sem_uri_falha_explicando_o_env(ambiente_fixture, monkeypatch):
    monkeypatch.setenv("DATASET_SOURCE", "s3")
    with pytest.raises(ValidationError, match="DATASET_S3_URI"):
        ConfigDados()


def test_config_recusa_tabela_que_nao_existe_na_camada_raw(ambiente_fixture, monkeypatch):
    monkeypatch.setenv("DATASET_TABLES", "complaints,reclamacoes")
    with pytest.raises(ValidationError, match="reclamacoes"):
        ConfigDados()


def test_config_separa_tabelas_por_virgula(ambiente_fixture):
    assert ConfigDados().dataset_tables == ["complaints", "branches"]


def test_preparar_fixture_carrega_so_as_tabelas_configuradas_e_e_idempotente(
    ambiente_fixture, banco_migrado, capsys
):
    preparar(banco_migrado, ConfigDados())
    assert contagens(banco_migrado) == (2, 1, 0)
    preparar(banco_migrado, ConfigDados())
    assert "já carregada" in capsys.readouterr().out
    assert contagens(banco_migrado) == (2, 1, 0)


def test_preparar_s3_baixa_carrega_e_depois_nao_consulta_o_bucket(
    ambiente_fixture, banco_migrado, tmp_path, monkeypatch
):
    raiz_original, _ = ambiente_fixture
    s3 = cliente()
    bucket = f"cli-{os.urandom(5).hex()}"
    s3.create_bucket(Bucket=bucket)
    for arquivo in raiz_original.rglob("*.csv"):
        s3.upload_file(str(arquivo), bucket, f"data/{arquivo.relative_to(raiz_original)}")
    destino = tmp_path / "baixado"
    monkeypatch.setenv("DATASET_SOURCE", "s3")
    monkeypatch.setenv("DATASET_RAW_DIR", str(destino))
    monkeypatch.setenv("DATASET_S3_URI", f"s3://{bucket}/data/")
    monkeypatch.setenv("DATASET_S3_ENDPOINT", os.environ["S3_TEST_ENDPOINT"])
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", os.environ["S3_TEST_ACCESS_KEY"])
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", os.environ["S3_TEST_SECRET_KEY"])
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    preparar(banco_migrado, ConfigDados())
    assert (destino / "branches.csv").read_bytes() == (raiz_original / "branches.csv").read_bytes()
    assert contagens(banco_migrado) == (2, 1, 0)

    # Versão já no banco: o bucket nem é consultado (objetos apagados não atrapalham).
    for objeto in s3.list_objects_v2(Bucket=bucket)["Contents"]:
        s3.delete_object(Bucket=bucket, Key=objeto["Key"])
    preparar(banco_migrado, ConfigDados())
    assert contagens(banco_migrado) == (2, 1, 0)


def test_cli_devolve_erro_e_mensagem_quando_arquivo_diverge(
    ambiente_fixture, banco_migrado, monkeypatch, capsys
):
    raiz, _ = ambiente_fixture
    (raiz / "branches.csv").write_text("adulterado", encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", banco_migrado.database_url)
    assert main(["jeje.dados", "preparar"]) == 1
    assert "branches.csv" in capsys.readouterr().err
    assert contagens(banco_migrado) == (0, 0, 0)
