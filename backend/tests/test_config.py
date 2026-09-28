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


def test_valor_do_ambiente_chega_ao_openapi_da_aplicacao(monkeypatch):
    monkeypatch.setenv("API_ROOT_PATH", "/api")  # demais variáveis vêm do compose de testes
    app = create_app(Settings())
    servidores = TestClient(app).get("/openapi.json").json()["servers"]
    assert servidores == [{"url": "/api"}]
