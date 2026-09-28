"""Fila do atendimento humano (console simulado): o resumo estruturado de cada encaminhamento
aberto, na ordem de chegada, e nada disso fora do modo demo."""

from conftest import abrir_conversa, autenticar, cliente, dizer


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
        "transaction_id": "TRX-A4", "data": "2025-03-15T11:00:00", "valor": "5000.00",
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
