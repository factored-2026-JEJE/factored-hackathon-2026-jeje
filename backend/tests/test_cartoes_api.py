"""Os cartões do cliente da sessão pela API real (o painel "Cartões" do app, DEV-032): só os dele,
com os 4 últimos dígitos e o bloqueio ativo do canal, nunca o número inteiro."""

from datetime import datetime

from conftest import autenticar, cliente, conexao, curar_tudo, raw_transacao
from sqlalchemy import text

from jeje import bloqueio, sessao


def test_cliente_ve_so_os_proprios_cartoes_com_o_bloqueio_ativo(cartoes):
    with conexao(cartoes) as con:
        for tid, cli, crt in (
            ("TRX-A1", "CLI-A", "CRT-A1"), ("TRX-B1", "CLI-B", "CRT-B1"),
            ("TRX-C1", "CLI-C", "CRT-C1"),
        ):  # fmt: skip
            raw_transacao(con, tid, cli, crt)
    curar_tudo(cartoes)
    with conexao(cartoes) as con:
        sessao.provisionar_personas(con, 3)
        completo, _ = bloqueio.bloquear(
            con, "CLI-A", "CRT-A1", "completo", "pedido", "cadastrado", 7
        )
        preventivo, _ = bloqueio.bloquear(con, "CLI-A", "CRT-A2", "preventivo", "pedido", "novo", 7)
        desfeito, _ = bloqueio.bloquear(
            con, "CLI-B", "CRT-B1", "completo", "pedido", "cadastrado", 7
        )
        con.execute(
            text("update app.bloqueios set desfeito_em = now(), desfeito_por = 'cliente'"
                 " where id = :id"), {"id": desfeito.id},
        )  # fmt: skip
    with cliente(cartoes) as http:
        de_a = http.get("/minhas/cartoes", headers=autenticar(http, "CLI-A"))
        # O cliente da URL não escolhe nada: vale o da sessão.
        de_b = http.get(
            "/minhas/cartoes", params={"customer_id": "CLI-A"}, headers=autenticar(http, "CLI-B")
        )
    assert (de_a.status_code, de_b.status_code) == (200, 200)
    # A conta PRD-A não é cartão; o fechado aparece com o status da base.
    assert [(c["product_id"], c["produto"], c["ultimos4"], c["status"]) for c in de_a.json()] == [
        ("CRT-A1", "Tarjeta Crédito", "9241", "Active"),
        ("CRT-A3", "Tarjeta Crédito", "0000", "Closed"),
        ("CRT-A2", "Tarjeta Débito", "5678", "Active"),
    ]
    bloqueios = [c["bloqueio"] for c in de_a.json()]
    assert [b and (b["id"], b["tipo"]) for b in bloqueios] == [
        (completo.id, "completo"), None, (preventivo.id, "preventivo")
    ]  # fmt: skip
    assert datetime.fromisoformat(bloqueios[0]["reversivel_ate"]) == completo.reversivel_ate
    # O bloqueio desfeito não aparece mais.
    assert de_b.json() == [
        {"product_id": "CRT-B1", "produto": "Tarjeta Crédito", "ultimos4": "1111",
         "status": "Active", "bloqueio": None}
    ]  # fmt: skip
    for numero in ("4000000000009241", "5000000000005678", "4111111111111111"):
        assert numero not in de_a.text + de_b.text
