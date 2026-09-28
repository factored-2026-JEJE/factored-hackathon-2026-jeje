"""Parâmetro de consulta repetido é recusado na borda, em toda rota (ACH-027)."""

import pytest
from conftest import autenticar, cliente


@pytest.mark.parametrize(
    "consulta", ["limite=abc&limite=3", "limite=3&limite=abc", "limite=3&limite=4"]
)
@pytest.mark.parametrize("rota", ["/minhas/transacoes", "/atendimento/fila"])
def test_parametro_de_consulta_repetido_e_recusado(cenario_conversa, rota, consulta):
    with cliente(cenario_conversa) as http:
        resposta = http.get(f"{rota}?{consulta}", headers=autenticar(http, "CLI-A"))
    assert resposta.status_code == 422
    [erro] = resposta.json()["detail"]
    assert (erro["type"], erro["loc"]) == ("parametro_repetido", ["query", "limite"])


def test_parametro_unico_ou_nao_declarado_segue_normal(cenario_conversa):
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        unico = http.get("/minhas/transacoes?limite=2", headers=auth)
        nao_declarado = http.get("/minhas/transacoes?limite=2&x=1&x=2", headers=auth)
    assert unico.status_code == nao_declarado.status_code == 200
    assert len(unico.json()) == len(nao_declarado.json()) == 2
