"""Sessão e autorização por dono pela API real (R08): identidade só pelo token da sessão."""

import re

import pytest
from conftest import cliente, conexao, curar_tudo, raw_transacao
from sqlalchemy import text

from jeje import bloqueio, sessao


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
    assert [(p["customer_id"], p["nome"]) for p in api.get("/personas").json()] == [
        ("CLI-A", "CLI-A"),
        ("CLI-C", "Ana Souza"),
    ]


def test_personas_trazem_dicas_para_escolher_o_caminho_da_demo(cartoes):
    """Para quem testa escolher a persona de cada caminho (PRD-009): cartões que ainda dá para
    bloquear, transações recusadas e pré-casos dentro da janela da reincidência (POL-HUM-06)."""
    with conexao(cartoes) as con:
        raw_transacao(con, "TRX-A1", "CLI-A", "CRT-A1", transaction_status="Declined")
        raw_transacao(con, "TRX-A2", "CLI-A", "CRT-A1")
        raw_transacao(con, "TRX-B1", "CLI-B", "CRT-B1", transaction_status="Declined")
        raw_transacao(con, "TRX-B2", "CLI-B", "CRT-B1", transaction_status="Declined")
        raw_transacao(con, "TRX-C1", "CLI-C", "CRT-C1")
    curar_tudo(cartoes)
    with conexao(cartoes) as con:
        sessao.provisionar_personas(con, 3)
        bloqueio.bloquear(con, "CLI-A", "CRT-A2", "completo", "pedido", "cadastrado", 7)
        con.execute(
            text(
                "INSERT INTO app.pre_casos (protocolo, customer_id, transaction_id, proposta_id,"
                " criado_em) VALUES ('PC-1', 'CLI-B', 'TRX-B1', 'P1', now()),"
                " ('PC-2', 'CLI-B', 'TRX-B2', 'P2', now() - interval '31 days')"
            )
        )
    with cliente(cartoes) as http:
        dicas = {
            p["customer_id"]: (
                p["cartoes_bloqueaveis"],
                p["transacoes_recusadas"],
                p["pre_casos_recentes"],
            )
            for p in http.get("/personas").json()
        }
    # CLI-A: dois cartões ativos, um já bloqueado por aqui; o fechado não conta.
    assert dicas == {"CLI-A": (1, 1, 0), "CLI-B": (1, 2, 1), "CLI-C": (0, 0, 0)}


def test_sessao_identifica_o_cliente_e_lista_so_as_transacoes_dele(api):
    cabecalho = entrar(api, "CLI-C")
    assert api.get("/sessao", headers=cabecalho).json() == {
        "customer_id": "CLI-C",
        "nome": "Ana Souza",
        "dispositivo": "novo",
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


@pytest.mark.parametrize("identificador", ["CLI-A\x00", "CLI A", "", "x" * 65, "CLI-Ã"])
def test_identificador_fora_do_formato_e_422_e_nunca_500(api, identificador):
    assert api.post("/sessoes", json={"customer_id": identificador}).status_code == 422


def test_transacao_com_nul_no_endereco_e_422_e_nunca_500(api):
    cabecalho = entrar(api, "CLI-A")
    assert api.get("/minhas/transacoes/TRX%00A1", headers=cabecalho).status_code == 422


# Rotas sem sessão de propósito: saúde, agregados sem dado de cliente, o acesso de demonstração
# (esses dois só com MODO_DEMO), o acesso dos jurados (a senha da publicação, PRD-009) e o portão de
# intenção de Enzo (só classifica o texto recebido). Rota nova fica fora daqui e, portanto, precisa
# exigir sessão.
PUBLICAS = {
    ("GET", "/health"), ("GET", "/health/ready"), ("GET", "/acesso"), ("POST", "/acesso/entrada"),
    ("POST", "/intencao/classificar"), ("GET", "/intencao/modelo"), ("GET", "/dados/eda"),
    ("GET", "/dados/qualidade"), ("GET", "/metricas"), ("GET", "/personas"), ("POST", "/sessoes"),
    ("GET", "/testadores"),
    ("GET", "/atendimento/fila"), ("POST", "/atendimento/fila/{handoff_id}/assumir"),
    ("GET", "/atendimento/bloqueios"), ("POST", "/atendimento/bloqueios/{bloqueio_id}/desbloqueio"),
}  # fmt: skip


def test_toda_rota_fora_da_lista_publica_exige_sessao(api):
    """Inventário pelo contrato publicado: cada operação que não é pública recusa quem chega sem
    sessão com 401 (antes de validar parâmetro ou corpo) e declara o esquema Bearer."""
    contrato = api.get("/openapi.json").json()
    recusadas = []
    for caminho, operacoes in contrato["paths"].items():
        for metodo, operacao in operacoes.items():
            if (metodo.upper(), caminho) in PUBLICAS:
                continue
            url = re.sub(r"\{[^}]+\}", "X-1", caminho)
            status = api.request(metodo.upper(), url, json={}).status_code
            recusadas.append((metodo.upper(), caminho, status, "security" in operacao))
    fora_do_padrao = [r for r in recusadas if r[2] != 401 or not r[3]]
    assert recusadas and not fora_do_padrao, fora_do_padrao


def test_dispositivo_do_acesso_volta_na_sessao_e_valor_estranho_e_422(api):
    """A demo escolhe o dispositivo simulado no acesso (PRD-007); a sessão devolve o escolhido, sem
    escolha vale "novo", e um valor fora da lista nem chega ao banco."""
    aberta = api.post("/sessoes", json={"customer_id": "CLI-A", "dispositivo": "cadastrado"})
    sem_escolha = api.post("/sessoes", json={"customer_id": "CLI-A"})
    estranho = api.post("/sessoes", json={"customer_id": "CLI-A", "dispositivo": "confiavel"})
    assert (aberta.status_code, aberta.json()["dispositivo"]) == (201, "cadastrado")
    assert (sem_escolha.status_code, sem_escolha.json()["dispositivo"]) == (201, "novo")
    assert estranho.status_code == 422
    atual = api.get("/sessao", headers={"Authorization": f"Bearer {aberta.json()['token']}"})
    assert atual.json()["dispositivo"] == "cadastrado"
