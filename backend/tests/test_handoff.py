"""Encaminhamento para humano: campos, minimização, ordem da fila e isolamento por cliente."""

from datetime import datetime
from decimal import Decimal

from conftest import conexao

from jeje import handoff
from jeje.handoff import Acao, Encaminhamento
from jeje.mensagens import TransacaoVerificada

TRANSACAO = TransacaoVerificada(
    "TRX-1", datetime(2025, 3, 10, 14, 9), Decimal("189.77"), "USD", "Farmacia", "Declined"
)


def test_encaminhamento_leva_motivo_fatos_acoes_e_pendencias(banco_migrado):
    with conexao(banco_migrado) as con:
        identificador = handoff.registrar(con, Encaminhamento(
            customer_id="CLI-A", regra="POL-DISP-02", idioma="pt",
            pedido="Não reconheço essa compra", transacao=TRANSACAO,
            acoes=(Acao("avaliar_contestacao", "POL-DISP-02"),),
            pendencias=("confirmar com o cliente se a compra foi feita por terceiro",),
        ))  # fmt: skip
        [registro] = handoff.fila(con, 10)
    assert identificador == registro["id"] and identificador.startswith("AT-")
    assert registro["regra"] == "POL-DISP-02" and registro["idioma"] == "pt"
    assert registro["transacao"] == {
        "transaction_id": "TRX-1", "data": "2025-03-10T14:09:00", "valor": "189.77",
        "moeda": "USD", "comercio": "Farmacia", "status": "Declined",
    }  # fmt: skip
    assert registro["acoes"] == [{"acao": "avaliar_contestacao", "resultado": "POL-DISP-02"}]
    assert registro["pendencias"] == ["confirmar com o cliente se a compra foi feita por terceiro"]


def test_pedido_longo_e_truncado_para_minimizar_dados(banco_migrado):
    longo = "a" * 1000
    with conexao(banco_migrado) as con:
        handoff.registrar(con, Encaminhamento("CLI-A", "POL-HUM-03", "es", longo))
        [registro] = handoff.fila(con, 10)
    assert len(registro["pedido"]) == handoff.LIMITE_PEDIDO
    assert registro["pedido"].endswith("…")
    assert registro["transacao"] is None


def test_fila_atende_os_mais_antigos_primeiro(banco_migrado):
    with conexao(banco_migrado) as con:
        primeiro = handoff.registrar(con, Encaminhamento("CLI-A", "POL-HUM-03", "es", "1"))
    with conexao(banco_migrado) as con:
        segundo = handoff.registrar(con, Encaminhamento("CLI-B", "POL-HUM-01", "pt", "2"))
        assert [r["id"] for r in handoff.fila(con, 10)] == [primeiro, segundo]
        assert [r["id"] for r in handoff.fila(con, 1)] == [primeiro]
