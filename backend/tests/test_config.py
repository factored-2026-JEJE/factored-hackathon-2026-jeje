"""Configuração vem do ambiente e falha alto quando falta (ENG-003)."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from jeje.api import create_app
from jeje.config import Settings


def test_variavel_ausente_falha_nomeando_a_variavel(monkeypatch):
    monkeypatch.delenv("API_ROOT_PATH", raising=False)
    with pytest.raises(ValidationError) as erro:
        Settings()
    assert "api_root_path" in str(erro.value)


@pytest.mark.parametrize("valor", [None, "VERBOSE"])
def test_nivel_de_log_ausente_ou_invalido_falha(monkeypatch, valor):
    if valor is None:
        monkeypatch.delenv("LOG_LEVEL", raising=False)
    else:
        monkeypatch.setenv("LOG_LEVEL", valor)
    with pytest.raises(ValidationError) as erro:
        Settings()
    assert "log_level" in str(erro.value)


def test_valor_do_ambiente_chega_ao_openapi_da_aplicacao(monkeypatch):
    monkeypatch.setenv("API_ROOT_PATH", "/api")  # demais variáveis vêm do compose de testes
    with TestClient(create_app(Settings())) as http:
        servidores = http.get("/openapi.json").json()["servers"]
    assert servidores == [{"url": "/api"}]
