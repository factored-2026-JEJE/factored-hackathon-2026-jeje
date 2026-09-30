"""Bloqueio simulado de cartão (PRD-007) no banco real: só cartão ativo do próprio cliente, um
bloqueio ativo por cartão, só os 4 últimos dígitos gravados, prazo de reversão pela janela e
nenhum "bloqueado" sem releitura — sempre conferindo o estado do banco, não só o retorno."""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from conftest import CREDITO, DEBITO, conexao
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from jeje import bloqueio, politica


def bloquear(settings, cliente: str, cartao: str, janela_dias: int = 7):
    with conexao(settings) as con:
        return bloqueio.bloquear(
            con, cliente, cartao, "completo", "pedido", "cadastrado", janela_dias
        )


def gravados(settings) -> list[dict]:
    with conexao(settings) as con:
        linhas = con.execute(text("SELECT * FROM app.bloqueios ORDER BY criado_em, id")).mappings()
        return [dict(linha) for linha in linhas]


def cartoes_de(settings, cliente: str) -> list[politica.Cartao]:
    with conexao(settings) as con:
        return bloqueio.cartoes_do_cliente(con, cliente)


def test_bloqueio_de_cartao_ativo_grava_so_os_4_ultimos_digitos(cartoes):
    feito, criado = bloquear(cartoes, "CLI-A", "CRT-A1")
    assert criado is True
    assert re.fullmatch(r"BL-\d{8}", feito.id)
    assert (feito.product_id, feito.produto, feito.ultimos4) == ("CRT-A1", CREDITO, "9241")
    assert (feito.tipo, feito.motivo, feito.dispositivo) == ("completo", "pedido", "cadastrado")
    [linha] = gravados(cartoes)
    assert (linha["id"], linha["customer_id"], linha["ultimos4"]) == (feito.id, "CLI-A", "9241")
    assert (linha["desfeito_em"], linha["desfeito_por"]) == (None, None)
    assert not any("4000000000009241" in str(valor) for valor in linha.values())


def test_bloquear_de_novo_devolve_o_mesmo_sem_duplicar(cartoes):
    primeiro, criado = bloquear(cartoes, "CLI-A", "CRT-A1")
    segundo, de_novo = bloquear(cartoes, "CLI-A", "CRT-A1")
    assert (criado, de_novo) == (True, False)
    assert segundo == primeiro
    assert len(gravados(cartoes)) == 1


def test_bloqueios_simultaneos_do_mesmo_cartao_criam_um_so(cartoes):
    with ThreadPoolExecutor(max_workers=6) as executor:
        resultados = list(executor.map(lambda _: bloquear(cartoes, "CLI-A", "CRT-A1"), range(6)))
    assert sorted(criado for _, criado in resultados) == [False] * 5 + [True]
    assert len({feito.id for feito, _ in resultados}) == 1
    assert len(gravados(cartoes)) == 1


@pytest.mark.parametrize(
    ("cliente", "produto"),
    [
        ("CLI-A", "CRT-B1"),  # cartão ativo de outro cliente
        ("CLI-A", "PRD-A"),  # conta do cliente, não cartão
        ("CLI-A", "CRT-A3"),  # cartão fechado na base
        ("CLI-C", "CRT-C1"),  # cartão já bloqueado na base
        ("CLI-A", "CRT-XX"),  # cartão inexistente
    ],
)
def test_so_bloqueia_cartao_ativo_do_proprio_cliente(cartoes, cliente, produto):
    with pytest.raises(bloqueio.NaoBloqueavel):
        bloquear(cartoes, cliente, produto)
    assert gravados(cartoes) == []


@pytest.mark.parametrize("dias", [7, 3])
def test_prazo_de_reversao_conta_a_janela_a_partir_do_bloqueio(cartoes, dias):
    feito, _ = bloquear(cartoes, "CLI-A", "CRT-A2", janela_dias=dias)
    assert feito.reversivel_ate - feito.criado_em == timedelta(days=dias)


def test_cartoes_do_cliente_trazem_status_da_base_e_bloqueio_do_canal(cartoes):
    antes = cartoes_de(cartoes, "CLI-A")
    assert antes == [
        politica.Cartao("CRT-A1", CREDITO, "9241", "Active"),
        politica.Cartao("CRT-A3", CREDITO, "0000", "Closed"),
        politica.Cartao("CRT-A2", DEBITO, "5678", "Active"),
    ]
    feito, _ = bloquear(cartoes, "CLI-A", "CRT-A1")
    depois = cartoes_de(cartoes, "CLI-A")
    assert [c.bloqueio for c in depois] == [feito.id, None, None]
    assert [c.product_id for c in politica.bloqueaveis(depois)] == ["CRT-A2"]
    assert cartoes_de(cartoes, "CLI-B") == [politica.Cartao("CRT-B1", CREDITO, "1111", "Active")]


def test_bloqueio_desfeito_libera_um_bloqueio_novo(cartoes):
    antigo, _ = bloquear(cartoes, "CLI-A", "CRT-A1")
    with conexao(cartoes) as con:
        con.execute(
            text("UPDATE app.bloqueios SET desfeito_em = now(), desfeito_por = 'atendente'")
        )
    assert cartoes_de(cartoes, "CLI-A")[0].bloqueio is None
    novo, criado = bloquear(cartoes, "CLI-A", "CRT-A1")
    assert criado is True
    assert novo.id != antigo.id
    assert cartoes_de(cartoes, "CLI-A")[0].bloqueio == novo.id
    assert len(gravados(cartoes)) == 2


def test_gravacao_que_nao_se_confirma_nao_vira_bloqueio(cartoes):
    """Um gatilho que descarta a linha em silêncio (a escrita "some"): sem releitura, nada de dizer
    que bloqueou; um gatilho que falha propaga o erro. Nos dois casos, nada fica gravado."""
    descartar = (
        "create function app.descartar() returns trigger language plpgsql as"
        " $$ begin return null; end $$;"
        " create trigger descarte_injetado before insert on app.bloqueios"
        " for each row execute function app.descartar()"
    )
    falhar = (
        "create function app.falhar() returns trigger language plpgsql as"
        " $$ begin raise exception 'falha injetada na persistência'; end $$;"
        " create trigger falha_injetada before insert on app.bloqueios"
        " for each row execute function app.falhar()"
    )
    with conexao(cartoes) as con:
        con.execute(text(descartar))
    with pytest.raises(RuntimeError, match="nada foi bloqueado"):
        bloquear(cartoes, "CLI-A", "CRT-A1")
    with conexao(cartoes) as con:
        con.execute(text("drop trigger descarte_injetado on app.bloqueios"))
        con.execute(text(falhar))
    with pytest.raises(DBAPIError, match="falha injetada"):
        bloquear(cartoes, "CLI-A", "CRT-A1")
    assert gravados(cartoes) == []


def test_bloqueio_de_outro_cliente_e_igual_a_inexistente(cartoes):
    do_b, _ = bloquear(cartoes, "CLI-B", "CRT-B1")
    with conexao(cartoes) as con:
        assert bloqueio.ativo_do_cliente(con, "CLI-A", do_b.id) is None
        assert bloqueio.ativo_do_cliente(con, "CLI-B", do_b.id) == do_b
