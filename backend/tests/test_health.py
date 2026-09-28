"""Liveness e readiness contra a aplicação e o PostgreSQL reais."""

import time

from conftest import registrar_dataset
from fastapi.testclient import TestClient

from jeje.api import create_app
from jeje.config import Settings


def cliente(settings: Settings) -> TestClient:
    return TestClient(create_app(settings.model_copy(update={"api_root_path": ""})))


def test_health_responde_ok_com_versao_do_pacote():
    resposta = cliente(Settings()).get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "version": "0.1.0"}


def test_rota_inexistente_retorna_404():
    assert cliente(Settings()).get("/nao-existe").status_code == 404


def test_ready_com_dataset_carregado_devolve_versao_e_origem(banco_migrado):
    registrar_dataset(banco_migrado, version="abc123", source="fixture")
    resposta = cliente(banco_migrado).get("/health/ready")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "ready"
    assert corpo["database"] == "ok"
    assert (corpo["dataset"]["version"], corpo["dataset"]["source"]) == ("abc123", "fixture")


def test_ready_sem_dataset_carregado_nao_esta_pronto(banco_migrado):
    resposta = cliente(banco_migrado).get("/health/ready")
    assert resposta.status_code == 503
    assert resposta.json() == {"status": "unavailable", "database": "ok", "dataset": None}


def test_ready_com_banco_sem_migrations_nao_esta_pronto(banco_limpo):
    resposta = cliente(banco_limpo).get("/health/ready")
    assert resposta.status_code == 503
    assert resposta.json()["database"] == "not_migrated"


def test_ready_com_banco_inacessivel_responde_503_rapido():
    settings = Settings(
        database_url="postgresql+psycopg://jeje:jeje@192.0.2.1:5432/nada",
        db_connect_timeout_s=1,
    )
    inicio = time.monotonic()
    resposta = cliente(settings).get("/health/ready")
    assert resposta.status_code == 503
    assert resposta.json() == {"status": "unavailable", "database": "unreachable", "dataset": None}
    assert time.monotonic() - inicio < 5
