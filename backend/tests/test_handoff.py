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


def test_o_caso_guarda_o_dispositivo_da_sessao_e_o_de_antes_fica_sem(banco_migrado):
    """2.1c: o dispositivo é um dos fatos do caso no design; o caso sem ele (os de antes) segue
    valendo."""
    with conexao(banco_migrado) as con:
        handoff.registrar(con, Encaminhamento("CLI-A", "POL-HUM-03", "es", "1", dispositivo="novo"))
        handoff.registrar(con, Encaminhamento("CLI-B", "POL-HUM-01", "pt", "2"))
        assert [r["dispositivo"] for r in handoff.fila(con, 10)] == ["novo", None]


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


# ---- texto do pedido escolhido por campos (DEV-036, NOV-11) ----

CAMPOS = {
    "No reconozco un cobro": {"pedido:contestar"},
    "Esto es un abuso, siempre pasa lo mismo.": set(),
    "Fue en Streaming Plus, de 45,90": {"comercio", "valor"},
    "Fue de 45,90": {"valor"},
    "Quiero hablar con una persona.": {"pedido:humano"},
}


def campos(fala: str) -> frozenset[str]:
    return frozenset(CAMPOS[fala])


def test_texto_do_pedido_junta_as_falas_com_campos_na_ordem_em_que_foram_ditas():
    falas = [
        "No reconozco un cobro",
        "Esto es un abuso, siempre pasa lo mismo.",
        "Fue en Streaming Plus, de 45,90",
        "Quiero hablar con una persona.",
    ]
    assert handoff.texto_por_campos(falas, campos) == (
        "No reconozco un cobro Fue en Streaming Plus, de 45,90 Quiero hablar con una persona."
    )


def test_no_limite_entra_primeiro_a_fala_com_mais_campos_novos():
    falas = ["No reconozco un cobro", "Fue en Streaming Plus, de 45,90", "Fue de 45,90"]
    # Cabem 33 caracteres: a fala com dois campos novos ganha da que tem um.
    assert handoff.texto_por_campos(falas, campos, limite=33) == "Fue en Streaming Plus, de 45,90"


def test_no_empate_de_campos_novos_entra_a_fala_mais_curta():
    falas = ["Fue en Streaming Plus, de 45,90", "Fue de 45,90"]
    so_valor = {"Fue en Streaming Plus, de 45,90": {"valor"}, "Fue de 45,90": {"valor"}}
    assert handoff.texto_por_campos(falas, lambda f: frozenset(so_valor[f])) == "Fue de 45,90"


def test_fala_sem_campo_novo_fica_de_fora_mesmo_cabendo():
    falas = ["Fue de 45,90", "No reconozco un cobro", "Fue de 45,90"]
    assert handoff.texto_por_campos(falas, campos) == "Fue de 45,90 No reconozco un cobro"


def test_sem_campo_em_nenhuma_fala_vai_a_primeira_como_hoje():
    falas = ["Esto es un abuso, siempre pasa lo mismo.", "no", "sí"]
    sem_campos = {f: set() for f in falas}
    assert handoff.texto_por_campos(falas, lambda f: frozenset(sem_campos[f])) == falas[0]


def test_texto_do_pedido_junta_as_falas_numa_linha_so():
    assert handoff.texto_por_campos(["  Fue de\n45,90 "], lambda f: frozenset({"valor"})) == (
        "Fue de 45,90"
    )
