"""Liveness e readiness contra a aplicação e o PostgreSQL reais."""

import time

from conftest import cliente, conexao, registrar_dataset
from sqlalchemy import text

from jeje.config import Settings


def test_health_responde_ok_com_versao_do_pacote():
    with cliente(Settings()) as http:
        resposta = http.get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "version": "0.1.0"}


def test_rota_inexistente_retorna_404():
    with cliente(Settings()) as http:
        assert http.get("/nao-existe").status_code == 404


def test_ready_com_dataset_carregado_devolve_versao_e_origem(banco_migrado):
    registrar_dataset(banco_migrado, version="abc123", source="fixture")
    with cliente(banco_migrado) as http:
        resposta = http.get("/health/ready")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "ready"
    assert corpo["database"] == "ok"
    assert (corpo["dataset"]["version"], corpo["dataset"]["source"]) == ("abc123", "fixture")


def test_ready_mostra_a_versao_recusada_e_segue_pronto_com_a_anterior(banco_migrado):
    """ACH-112: a versão nova recusada pela carga aparece na prontidão, que segue pronta com a
    anterior; sem recusa, o campo vem vazio."""
    registrar_dataset(banco_migrado, version="abc123", source="fixture")
    with cliente(banco_migrado) as http:
        antes = http.get("/health/ready").json()["dataset"]["recusada"]
    with conexao(banco_migrado) as con:
        con.execute(
            text(
                "update meta.dataset_version set recusada_versao = 'def456', "
                "recusada_motivo = 'coluna nova em branches', recusada_em = now()"
            )
        )
    with cliente(banco_migrado) as http:
        resposta = http.get("/health/ready")
    corpo = resposta.json()
    assert (resposta.status_code, corpo["status"], corpo["dataset"]["version"]) == (
        200, "ready", "abc123"
    )  # fmt: skip
    recusada = corpo["dataset"]["recusada"]
    assert (antes, recusada["version"], recusada["motivo"]) == (
        None, "def456", "coluna nova em branches"
    )  # fmt: skip
    assert recusada["em"]


def test_ready_sem_dataset_carregado_nao_esta_pronto(banco_migrado):
    with cliente(banco_migrado) as http:
        resposta = http.get("/health/ready")
    assert resposta.status_code == 503
    assert resposta.json() == {"status": "unavailable", "database": "ok", "dataset": None}


def test_ready_com_banco_sem_migrations_nao_esta_pronto(banco_limpo):
    with cliente(banco_limpo) as http:
        resposta = http.get("/health/ready")
    assert resposta.status_code == 503
    assert resposta.json()["database"] == "not_migrated"


def test_ready_com_banco_inacessivel_responde_503_rapido():
    settings = Settings(
        database_url="postgresql+psycopg://jeje:jeje@192.0.2.1:5432/nada",
        db_connect_timeout_s=1,
    )
    inicio = time.monotonic()
    with cliente(settings) as http:
        resposta = http.get("/health/ready")
    assert resposta.status_code == 503
    assert resposta.json() == {"status": "unavailable", "database": "unreachable", "dataset": None}
    assert time.monotonic() - inicio < 5
