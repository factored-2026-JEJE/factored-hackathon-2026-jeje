"""Smoke da fundação: a aplicação real sobe e expõe apenas as rotas declaradas."""

from fastapi.testclient import TestClient

from jeje.api import app

client = TestClient(app)


def test_health_responde_ok_com_versao_do_pacote():
    resposta = client.get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "version": "0.1.0"}


def test_rota_inexistente_retorna_404():
    assert client.get("/nao-existe").status_code == 404
