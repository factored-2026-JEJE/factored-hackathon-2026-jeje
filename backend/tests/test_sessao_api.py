"""Sessão e autorização por dono pela API real (R08): identidade só pelo token da sessão."""

import pytest
from conftest import cliente, conexao
from sqlalchemy import text

from jeje import sessao


@pytest.fixture
def api(curada):
    with conexao(curada) as con:
        sessao.provisionar_personas(con, 2)  # CLI-A e CLI-C (CLI-B fica sem persona)
    with cliente(curada) as http:
        yield http


def entrar(http, customer_id: str) -> dict:
    resposta = http.post("/sessoes", json={"customer_id": customer_id})
    assert resposta.status_code == 201, resposta.text
    return {"Authorization": f"Bearer {resposta.json()['token']}"}


def test_personas_listadas_na_ordem_provisionada(api):
    assert api.get("/personas").json() == [
        {"customer_id": "CLI-A", "nome": "CLI-A"},
        {"customer_id": "CLI-C", "nome": "Ana Souza"},
    ]


def test_sessao_identifica_o_cliente_e_lista_so_as_transacoes_dele(api):
    cabecalho = entrar(api, "CLI-C")
    assert api.get("/sessao", headers=cabecalho).json() == {
        "customer_id": "CLI-C",
        "nome": "Ana Souza",
    }
    ids = [t["transaction_id"] for t in api.get("/minhas/transacoes", headers=cabecalho).json()]
    assert sorted(ids) == ["TRX-C1", "TRX-C2"]


def test_transacao_de_outro_cliente_responde_igual_a_inexistente(api):
    cabecalho = entrar(api, "CLI-A")
    alheia = api.get("/minhas/transacoes/TRX-C1", headers=cabecalho)
    inexistente = api.get("/minhas/transacoes/TRX-NAO-EXISTE", headers=cabecalho)
    assert alheia.status_code == inexistente.status_code == 404
    assert alheia.json() == inexistente.json() == {"detail": "Transação não encontrada"}
    assert api.get("/minhas/transacoes/TRX-A1", headers=cabecalho).json()["amount"] == "189.77"


def test_cliente_escolhido_na_url_e_ignorado(api):
    cabecalho = entrar(api, "CLI-A")
    resposta = api.get("/minhas/transacoes?customer_id=CLI-C", headers=cabecalho)
    assert {t["transaction_id"] for t in resposta.json()} == {"TRX-A1", "TRX-A2"}


@pytest.mark.parametrize(
    "cabecalho",
    [{}, {"Authorization": "Bearer inventado"}, {"Authorization": "Basic Q0xJLUE6eA=="}],
    ids=["sem-token", "token-inventado", "outro-esquema"],
)
def test_sem_sessao_valida_nao_ha_dados(api, cabecalho):
    resposta = api.get("/minhas/transacoes", headers=cabecalho)
    assert resposta.status_code == 401
    assert resposta.headers["www-authenticate"] == "Bearer"


def test_sessao_expirada_e_recusada(api, curada):
    cabecalho = entrar(api, "CLI-A")
    with conexao(curada) as con:
        con.execute(text("update app.sessoes set expira_em = now() - interval '1 second'"))
    assert api.get("/minhas/transacoes", headers=cabecalho).status_code == 401


def test_so_persona_provisionada_abre_sessao(api):
    assert api.post("/sessoes", json={"customer_id": "CLI-B"}).status_code == 404
    assert api.post("/sessoes", json={"customer_id": "CLI-INVENTADO"}).status_code == 404


def test_modo_demo_desligado_esconde_personas_e_sessoes(curada):
    with conexao(curada) as con:
        sessao.provisionar_personas(con, 2)
    with cliente(curada.model_copy(update={"modo_demo": False})) as http:
        assert http.get("/personas").status_code == 404
        assert http.post("/sessoes", json={"customer_id": "CLI-A"}).status_code == 404


def test_limite_restringe_a_listagem(api):
    cabecalho = entrar(api, "CLI-A")
    assert len(api.get("/minhas/transacoes?limite=1", headers=cabecalho).json()) == 1
    assert api.get("/minhas/transacoes?limite=0", headers=cabecalho).status_code == 422
