"""Configuração e orquestração do pipeline de dados (o que o serviço seed executa)."""

import os

import pytest
from conftest import conexao
from pydantic import ValidationError
from sqlalchemy import text
from test_carga import escrever_csv
from test_download import cliente

from jeje import consultas
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
        "PERSONAS_QUANTIDADE": "3",
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


def recusa(settings) -> tuple:
    with conexao(settings) as con:
        consulta = "select version, recusada_versao, recusada_motivo from meta.dataset_version"
        return tuple(con.execute(text(consulta)).one())


def test_versao_nova_recusada_mantem_a_anterior_e_o_seed_segue(
    ambiente_fixture, banco_migrado, monkeypatch, capsys
):
    """ACH-112: com uma versão carregada, a nova que o contrato recusa (coluna nova, manifesto
    regenerado) não derruba o serviço: o seed sai com 0, a anterior continua valendo e a recusa
    fica gravada para a prontidão. A próxima carga boa apaga a recusa."""
    raiz, manifestos = ambiente_fixture
    monkeypatch.setenv("DATABASE_URL", banco_migrado.database_url)
    assert main(["jeje.dados", "preparar"]) == 0
    anterior = recusa(banco_migrado)[0]

    (raiz / "branches.csv").write_text("branch_id,coluna_nova\nSUC-1,x\n", encoding="utf-8")
    manifesto.escrever(manifestos, manifesto.gerar(raiz, ["complaints", "branches"]))
    nova = manifesto.versao(manifestos, ["complaints", "branches"])
    capsys.readouterr()
    assert main(["jeje.dados", "preparar"]) == 0
    assert f"versão {nova[:12]} recusada" in capsys.readouterr().err
    versao, recusada, motivo = recusa(banco_migrado)
    assert (versao, recusada, contagens(banco_migrado)) == (anterior, nova, (2, 1, 0))
    assert "branches" in motivo

    escrever_csv(raiz, "branches.csv", "branches", [{"branch_id": "SUC-1"}, {"branch_id": "SUC-2"}])
    manifesto.escrever(manifestos, manifesto.gerar(raiz, ["complaints", "branches"]))
    assert main(["jeje.dados", "preparar"]) == 0
    assert recusa(banco_migrado)[1:] == (None, None)
    assert contagens(banco_migrado) == (2, 2, 0)


def test_preparar_recarrega_quando_o_pipeline_gravado_e_antigo(
    ambiente_fixture, banco_migrado, capsys
):
    preparar(banco_migrado, ConfigDados())
    with conexao(banco_migrado) as con:
        con.execute(text("update meta.dataset_version set pipeline = 'versao-antiga-do-codigo'"))
    capsys.readouterr()
    preparar(banco_migrado, ConfigDados())
    assert "carregada (fixture)" in capsys.readouterr().out
    with conexao(banco_migrado) as con:
        assert con.execute(text("select pipeline from meta.dataset_version")).scalar_one() != (
            "versao-antiga-do-codigo"
        )


def test_preparar_provisiona_personas_mesmo_quando_a_carga_e_pulada(
    ambiente_fixture, banco_migrado, tmp_path, monkeypatch
):
    raiz, _ = ambiente_fixture
    escrever_csv(raiz, "customers.csv", "customers", [{"customer_id": "CLI-A"}])
    escrever_csv(raiz, "products.csv", "products", [
        {"product_id": "PRD-A", "customer_id": "CLI-A", "product_type": "Cuenta Ahorro",
         "currency": "USD", "product_status": "Active"},
    ])  # fmt: skip
    escrever_csv(raiz, "transactions/year=2025/month=03/day=10/t.csv", "transactions", [
        {"transaction_id": "TRX-1", "transaction_date": "2025-03-10 10:00:00",
         "customer_id": "CLI-A", "product_id": "PRD-A", "amount": "1.00", "currency": "USD",
         "transaction_status": "Approved"},
    ])  # fmt: skip
    tabelas = "customers,products,transactions"
    manifestos = tmp_path / "manifesto-trx"
    manifesto.escrever(manifestos, manifesto.gerar(raiz, tabelas.split(",")))
    monkeypatch.setenv("DATASET_TABLES", tabelas)
    monkeypatch.setenv("DATASET_MANIFEST_DIR", str(manifestos))
    preparar(banco_migrado, ConfigDados())
    with conexao(banco_migrado) as con:
        con.execute(text("delete from app.personas"))
    preparar(banco_migrado, ConfigDados())  # carga pulada; personas voltam
    with conexao(banco_migrado) as con:
        assert con.execute(text("select customer_id from app.personas")).scalars().all() == [
            "CLI-A"
        ]


def test_recibo_aponta_a_linha_fisica_do_csv_de_origem(
    ambiente_fixture, banco_migrado, tmp_path, monkeypatch
):
    """ACH-180 (DEV-081): quem confere o recibo no editor ou com `sed -n Np` acha a transação
    citada na linha que ele diz, contando o cabeçalho como a linha 1."""
    raiz, _ = ambiente_fixture
    escrever_csv(raiz, "customers.csv", "customers", [{"customer_id": "CLI-A"}])
    escrever_csv(raiz, "products.csv", "products", [
        {"product_id": "PRD-A", "customer_id": "CLI-A", "product_type": "Cuenta Ahorro",
         "currency": "USD", "product_status": "Active"},
    ])  # fmt: skip
    caminho = "transactions/year=2025/month=03/day=10/t.csv"
    escrever_csv(raiz, caminho, "transactions", [
        {"transaction_id": f"TRX-{n}", "transaction_date": "2025-03-10 10:00:00",
         "customer_id": "CLI-A", "product_id": "PRD-A", "amount": f"{n}.00", "currency": "USD",
         "transaction_status": "Approved"}
        for n in (1, 2, 3)
    ])  # fmt: skip
    tabelas = "customers,products,transactions"
    manifestos = tmp_path / "manifesto-trx"
    manifesto.escrever(manifestos, manifesto.gerar(raiz, tabelas.split(",")))
    monkeypatch.setenv("DATASET_TABLES", tabelas)
    monkeypatch.setenv("DATASET_MANIFEST_DIR", str(manifestos))
    preparar(banco_migrado, ConfigDados())
    with conexao(banco_migrado) as con:
        origem = consultas.origem_da_transacao(con, "CLI-A", "TRX-2")
    linhas = (raiz / origem.arquivo).read_text(encoding="utf-8-sig").splitlines()
    assert linhas[origem.linha - 1].startswith("TRX-2,")
