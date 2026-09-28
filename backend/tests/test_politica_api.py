"""Política exposta pela API com fatos da curada e sessão real (sem efeito colateral)."""

from decimal import Decimal

import pytest
from conftest import cliente, conexao, curar_tudo, raw_transacao

from jeje import sessao


@pytest.fixture
def cenario(base):
    with conexao(base) as con:
        raw_transacao(
            con, "TRX-51", "CLI-A", "PRD-A", transaction_status="Declined", response_code="51"
        )
        raw_transacao(con, "TRX-PEND", "CLI-A", "PRD-A", transaction_status="Pending")
        raw_transacao(con, "TRX-USD", "CLI-A", "PRD-A", amount="189.77")
        raw_transacao(
            con, "TRX-COP", "CLI-A", "PRD-A", currency="COP", amount="200000.00", amount_usd="48.40"
        )
        raw_transacao(con, "TRX-COP-SEM-USD", "CLI-A", "PRD-A", currency="COP", amount="10.00")
        raw_transacao(con, "TRX-ALTA", "CLI-A", "PRD-A", amount="7500.00")
        raw_transacao(
            con, "TRX-TRF", "CLI-A", "PRD-A", transaction_type="Transfer", amount="60000.00"
        )
        raw_transacao(
            con, "TRX-NOITE", "CLI-A", "PRD-A", channel="App", amount="300.00",
            transaction_date="2025-03-10 22:30:00",
        )  # fmt: skip
        raw_transacao(con, "TRX-DE-B", "CLI-B", "PRD-B")
    curar_tudo(base)
    with conexao(base) as con:
        sessao.provisionar_personas(con, 2)
    return base


def chamar(settings, caminho: str):
    with cliente(settings) as http:
        token = http.post("/sessoes", json={"customer_id": "CLI-A"}).json()["token"]
        return http.get(caminho, headers={"Authorization": f"Bearer {token}"})


def decisao(settings, caminho: str) -> tuple:
    corpo = chamar(settings, caminho).json()
    d = corpo.get("decisao", corpo)
    return d["regra"], d["acao"], d["detalhe"]


def test_situacao_de_recusa_com_codigo_catalogado_explica_o_codigo(cenario):
    resposta = chamar(cenario, "/minhas/transacoes/TRX-51/situacao").json()
    assert resposta["transacao"]["transaction_id"] == "TRX-51"
    assert (resposta["decisao"]["regra"], resposta["decisao"]["detalhe"]) == ("POL-CON-03", "51")


def test_situacao_de_pendente_informa_sem_prometer(cenario):
    assert decisao(cenario, "/minhas/transacoes/TRX-PEND/situacao") == (
        "POL-CON-05", "responder", "Pending",
    )  # fmt: skip


@pytest.mark.parametrize(
    ("transacao", "esperado"),
    [
        ("TRX-USD", ("POL-DISP-01", "propor_pre_caso", None)),
        ("TRX-COP", ("POL-DISP-01", "propor_pre_caso", None)),
        ("TRX-COP-SEM-USD", ("POL-HUM-02", "humano", "valor em USD indisponível")),
        ("TRX-ALTA", ("POL-HUM-02", "humano", "acima do limite simulado")),
        ("TRX-51", ("POL-DISP-02", "humano", "Declined")),
        ("TRX-TRF", ("POL-SEG-01", "humano", "transferência acima do limite de segurança")),
        ("TRX-NOITE", ("POL-DISP-01", "propor_pre_caso", None)),
    ],
)
def test_contestacao_avaliada_pelos_fatos_da_curada(cenario, transacao, esperado):
    assert decisao(cenario, f"/minhas/transacoes/{transacao}/contestacao") == esperado


@pytest.mark.parametrize("sufixo", ["situacao", "contestacao"])
def test_transacao_de_outro_cliente_nao_e_avaliada(cenario, sufixo):
    alheia = chamar(cenario, f"/minhas/transacoes/TRX-DE-B/{sufixo}")
    inexistente = chamar(cenario, f"/minhas/transacoes/TRX-NADA/{sufixo}")
    assert alheia.status_code == inexistente.status_code == 404
    assert alheia.json() == inexistente.json()


def test_limite_vem_da_configuracao(cenario):
    com_limite_baixo = cenario.model_copy(update={"limite_pre_caso_usd": Decimal("100")})
    assert decisao(com_limite_baixo, "/minhas/transacoes/TRX-USD/contestacao") == (
        "POL-HUM-02", "humano", "acima do limite simulado",
    )  # fmt: skip


def test_transferencia_atipica_vai_para_seguranca_tambem_na_situacao(cenario):
    assert decisao(cenario, "/minhas/transacoes/TRX-TRF/situacao") == (
        "POL-SEG-01", "humano", "transferência acima do limite de segurança",
    )  # fmt: skip


BAIXO = Decimal("100")


@pytest.mark.parametrize(
    ("ajuste", "esperado"),
    [
        ({"limite_noturno_usd": BAIXO}, "POL-HUM-04"),
        ({"limite_noturno_dia_usd": BAIXO}, "POL-HUM-04"),
        # Com o limite noturno baixo, só deixa de valer se a compra sair da regra noturna:
        ({"limite_noturno_usd": BAIXO, "noturno_inicio_h": 23}, "POL-DISP-01"),
        ({"limite_noturno_usd": BAIXO, "canais_digitais": "Web"}, "POL-DISP-01"),
        ({"limite_noturno_usd": BAIXO, "canais_digitais": "Web, App"}, "POL-HUM-04"),
    ],
)
def test_limites_noturnos_vem_da_configuracao(cenario, ajuste, esperado):
    """A mesma compra de USD 300 às 22h30 pelo app, com limites do compose ajustados por caso."""
    ajustado = cenario.model_copy(update=ajuste)
    assert decisao(ajustado, "/minhas/transacoes/TRX-NOITE/contestacao")[0] == esperado


def test_limite_de_seguranca_vem_da_configuracao(cenario):
    ajustado = cenario.model_copy(update={"limite_seguranca_transferencia_usd": Decimal("70000")})
    assert decisao(ajustado, "/minhas/transacoes/TRX-TRF/contestacao")[0] == "POL-HUM-02"
