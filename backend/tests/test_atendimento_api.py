"""Fila do atendimento humano (console simulado): o resumo estruturado de cada encaminhamento
aberto, na ordem de chegada, e nada disso fora do modo demo."""

from concurrent.futures import ThreadPoolExecutor

import httpx2 as httpx
from conftest import abrir_conversa, autenticar, cliente, conexao, dizer, servidor_http
from sqlalchemy import text


def test_fila_mostra_os_encaminhamentos_com_o_resumo_na_ordem(cenario_conversa):
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        fraude = dizer(http, auth, abrir_conversa(http, auth, "pt"), "roubaram meu cartão")
        limite = dizer(
            http, auth, abrir_conversa(http, auth, "es"), "No reconozco la compra en Boutique Moda"
        )
        fila = http.get("/atendimento/fila").json()
    assert [e["id"] for e in fila] == [fraude["atendimento"], limite["atendimento"]]
    primeiro, segundo = fila
    assert (primeiro["regra"], primeiro["idioma"], primeiro["pedido"], primeiro["transacao"]) == (
        "POL-HUM-01", "pt", "roubaram meu cartão", None
    )  # fmt: skip
    assert (segundo["regra"], segundo["customer_id"], segundo["estado"]) == (
        "POL-HUM-02", "CLI-A", "aberto"
    )  # fmt: skip
    assert segundo["transacao"] == {
        "transaction_id": "TRX-A4", "data": "2025-03-15T11:00:00", "valor": "7500.00",
        "moeda": "USD", "comercio": "Boutique Moda", "status": "Approved",
    }  # fmt: skip
    assert segundo["acoes"] == [
        {"acao": "identificar_transacao", "resultado": "TRX-A4 (Approved)"},
        {"acao": "avaliar_contestacao", "resultado": "POL-HUM-02: acima do limite simulado"},
    ]
    assert segundo["pendencias"] == [
        "Revisar contestação que a automação não pode registrar (acima do limite simulado)"
    ]


def test_fila_nao_existe_fora_do_modo_demo(cenario_conversa):
    with cliente(cenario_conversa.model_copy(update={"modo_demo": False})) as http:
        resposta = http.get("/atendimento/fila")
    assert resposta.status_code == 404


def encaminhar(http, auth, relato: str = "me robaron la tarjeta") -> str:
    return dizer(http, auth, abrir_conversa(http, auth, "es"), relato)["atendimento"]


def test_assumir_tira_da_fila_e_ninguem_assume_duas_vezes(cenario_conversa):
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        primeiro, segundo = encaminhar(http, auth), encaminhar(http, auth)
        assumido = http.post(f"/atendimento/fila/{primeiro}/assumir")
        de_novo = http.post(f"/atendimento/fila/{primeiro}/assumir")
        inexistente = http.post("/atendimento/fila/AT-99999999/assumir")
        fila = http.get("/atendimento/fila").json()
    assert assumido.status_code == 200
    assert (assumido.json()["id"], assumido.json()["estado"]) == (primeiro, "em_atendimento")
    assert (de_novo.status_code, inexistente.status_code) == (409, 404)
    assert [e["id"] for e in fila] == [segundo]


def test_dois_atendentes_ao_mesmo_tempo_so_um_assume(cenario_conversa):
    with servidor_http(cenario_conversa) as url, httpx.Client(base_url=url) as http:
        auth = autenticar(http, "CLI-A")
        atendimento = encaminhar(http, auth)
        with ThreadPoolExecutor(max_workers=4) as grupo:
            respostas = list(
                grupo.map(lambda _: http.post(f"/atendimento/fila/{atendimento}/assumir"), range(4))
            )
    assert sorted(r.status_code for r in respostas) == [200, 409, 409, 409]


def test_assumir_nao_existe_fora_do_modo_demo(cenario_conversa):
    with cliente(cenario_conversa) as http:
        atendimento = encaminhar(http, autenticar(http, "CLI-A"))
    with cliente(cenario_conversa.model_copy(update={"modo_demo": False})) as http:
        resposta = http.post(f"/atendimento/fila/{atendimento}/assumir")
    assert resposta.status_code == 404


def test_assumir_deixa_evento_com_o_atendimento_e_a_regra(cenario_conversa):
    """Auditoria: quem assumiu o caso não é um turno da conversa, mas é um efeito e deixa trace."""
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        atendimento = dizer(http, auth, abrir_conversa(http, auth, "es"), "Me robaron la tarjeta")[
            "atendimento"
        ]
        assumido = http.post(f"/atendimento/fila/{atendimento}/assumir")
    with conexao(cenario_conversa) as con:
        consulta = "SELECT acao, efeito, regra FROM app.eventos WHERE tipo = 'acao'"
        acoes = [tuple(linha) for linha in con.execute(text(consulta))]
    assert assumido.status_code == 200
    assert acoes == [("assumir_atendimento", atendimento, "POL-HUM-01")]
