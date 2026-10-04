"""Fila do atendimento humano (console simulado): o resumo estruturado de cada encaminhamento
aberto, na ordem de chegada, e nada disso fora do modo demo."""

from concurrent.futures import ThreadPoolExecutor

import httpx2 as httpx
from conftest import abrir_conversa, autenticar, cliente, conexao, dizer, servidor_http
from sqlalchemy import text

from jeje import bloqueio


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


def test_o_caso_da_conversa_leva_o_dispositivo_da_sessao(cenario_conversa):
    """2.1c: o dispositivo escolhido no acesso chega ao caso, e a sessão sem escolha é "novo"."""
    with cliente(cenario_conversa) as http:
        token = http.post("/sessoes", json={"customer_id": "CLI-A", "dispositivo": "cadastrado"})
        cadastrado = {"Authorization": f"Bearer {token.json()['token']}"}
        novo = autenticar(http, "CLI-A")
        pessoa = "Quiero hablar con una persona"
        dizer(http, cadastrado, abrir_conversa(http, cadastrado, "es"), pessoa)
        dizer(http, novo, abrir_conversa(http, novo, "pt"), "Quero falar com um atendente")
        fila = http.get("/atendimento/fila").json()
    assert [(e["regra"], e["dispositivo"]) for e in fila] == [
        ("POL-HUM-03", "cadastrado"), ("POL-HUM-03", "novo")
    ]  # fmt: skip


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


# ---- Bloqueios de cartão (PRD-007) --------------------------------------------------------------


def bloquear(settings, cliente_id: str, cartao: str, dispositivo: str = "cadastrado") -> str:
    """Bloqueio feito direto pelo módulo (a conversa ainda não bloqueia neste passo)."""
    with conexao(settings) as con:
        feito, _ = bloqueio.bloquear(con, cliente_id, cartao, "completo", "pedido", dispositivo, 7)
    return feito.id


def eventos_de_desbloqueio(settings) -> list[tuple]:
    with conexao(settings) as con:
        return [
            tuple(linha)
            for linha in con.execute(
                text(
                    "select acao, regra, efeito, fontes from app.eventos"
                    " where tipo = 'acao' and acao = 'desbloquear_cartao'"
                )
            )
        ]


def test_console_mostra_os_bloqueios_ativos_mais_recentes_primeiro(cartoes):
    a1, a2, b1 = (bloquear(cartoes, "CLI-A", "CRT-A1"), bloquear(cartoes, "CLI-A", "CRT-A2"),
                  bloquear(cartoes, "CLI-B", "CRT-B1", "novo"))  # fmt: skip
    with conexao(cartoes) as con:
        con.execute(
            text("update app.bloqueios set desfeito_em = now(), desfeito_por = 'cliente'"
                 " where id = :id"), {"id": a2},
        )  # fmt: skip
    with cliente(cartoes) as http:
        lista = http.get("/atendimento/bloqueios")
        so_um = http.get("/atendimento/bloqueios", params={"limite": 1}).json()
    assert lista.status_code == 200
    assert [b["id"] for b in lista.json()] == [b1, a1]
    assert [b["id"] for b in so_um] == [b1]
    recente = lista.json()[0]
    assert (recente["customer_id"], recente["produto"], recente["ultimos4"]) == (
        "CLI-B", "Tarjeta Crédito", "1111"
    )  # fmt: skip
    assert (recente["tipo"], recente["motivo"], recente["dispositivo"]) == (
        "completo", "pedido", "novo"
    )  # fmt: skip
    assert (recente["desfeito_em"], recente["desfeito_por"]) == (None, None)
    assert recente["atendimento"] is None  # bloqueio sem caso do atendente
    assert "4111111111111111" not in lista.text


def test_atendente_desbloqueia_uma_vez_e_fica_o_evento(cartoes):
    feito = bloquear(cartoes, "CLI-A", "CRT-A1")
    with cliente(cartoes) as http:
        desfeito = http.post(f"/atendimento/bloqueios/{feito}/desbloqueio")
        de_novo = http.post(f"/atendimento/bloqueios/{feito}/desbloqueio")
        inexistente = http.post("/atendimento/bloqueios/BL-99999999/desbloqueio")
        lista = http.get("/atendimento/bloqueios").json()
    assert desfeito.status_code == 200
    corpo = desfeito.json()
    assert (corpo["id"], corpo["desfeito_por"]) == (feito, "atendente")
    assert corpo["desfeito_em"] is not None
    assert (de_novo.status_code, inexistente.status_code) == (409, 404)
    assert lista == []
    assert eventos_de_desbloqueio(cartoes) == [
        ("desbloquear_cartao", "POL-BLQ-05", feito, ["app.bloqueios"])
    ]
    with conexao(cartoes) as con:
        [a1, *_] = bloqueio.cartoes_do_cliente(con, "CLI-A")
    assert (a1.product_id, a1.bloqueio) == ("CRT-A1", None)


def test_dois_atendentes_ao_mesmo_tempo_desbloqueiam_uma_vez_so(cartoes):
    feito = bloquear(cartoes, "CLI-A", "CRT-A1")
    with servidor_http(cartoes) as url:
        alvo = f"{url}/atendimento/bloqueios/{feito}/desbloqueio"
        with ThreadPoolExecutor(max_workers=6) as executor:
            respostas = list(executor.map(lambda _: httpx.post(alvo), range(6)))
    assert sorted(r.status_code for r in respostas) == [200] + [409] * 5
    assert len(eventos_de_desbloqueio(cartoes)) == 1


def test_bloqueios_nao_existem_fora_do_modo_demo(cartoes):
    feito = bloquear(cartoes, "CLI-A", "CRT-A1")
    with cliente(cartoes.model_copy(update={"modo_demo": False})) as http:
        lista = http.get("/atendimento/bloqueios")
        desfeito = http.post(f"/atendimento/bloqueios/{feito}/desbloqueio")
    assert (lista.status_code, desfeito.status_code) == (404, 404)
    assert eventos_de_desbloqueio(cartoes) == []
