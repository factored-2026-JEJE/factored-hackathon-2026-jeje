"""Limpeza dos dados de teste da demonstração (ACH-040) no banco real: sai o estado do canal, ficam
a base, as personas e as reviews do time com as conversas avaliadas, e as sequências não voltam."""

import pytest
from conftest import abrir_conversa, cliente, conexao, curar_tudo, dizer, raw_transacao
from sqlalchemy import text

from jeje import limpeza, sessao

ESQUEMAS = ("app", "curated", "raw", "meta", "quality")


def contagens(settings) -> dict[str, int]:
    with conexao(settings) as con:
        tabelas = con.execute(
            text(
                "SELECT table_schema || '.' || table_name FROM information_schema.tables"
                " WHERE table_schema = ANY(:esquemas) AND table_type = 'BASE TABLE'"
            ),
            {"esquemas": list(ESQUEMAS)},
        ).scalars()
        return {t: con.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in tabelas}


def entrar(http, cliente_id: str) -> dict:
    corpo = {"customer_id": cliente_id, "dispositivo": "cadastrado"}
    return {"Authorization": f"Bearer {http.post('/sessoes', json=corpo).json()['token']}"}


@pytest.fixture
def usada(cartoes):
    """A demo depois de uma rodada de testes: um pré-caso, um relato de roubo com bloqueio e caso,
    uma conversa avaliada pelo time e os eventos de tudo isso."""
    with conexao(cartoes) as con:
        raw_transacao(con, "TRX-A1", "CLI-A", "CRT-A1", amount="45.90")
        raw_transacao(con, "TRX-B1", "CLI-B", "CRT-B1")
    curar_tudo(cartoes)
    with conexao(cartoes) as con:
        sessao.provisionar_personas(con, 3)
    with cliente(cartoes) as http:
        a = entrar(http, "CLI-A")
        conversa = abrir_conversa(http, a, "es")
        dizer(http, a, conversa, "No reconozco el cobro de 45,90 del 10/03")
        assert dizer(http, a, conversa, "Sí, confirmo")["protocolo"]
        b = entrar(http, "CLI-B")
        avaliada = abrir_conversa(http, b, "es")
        assert dizer(http, b, avaliada, "me robaron la tarjeta")["bloqueio"]
    with conexao(cartoes) as con:
        con.execute(
            text(
                "INSERT INTO app.reviews (conversa_id, avaliador, nota, resolveu, comentario)"
                " VALUES (:conversa, 'enzo200325', 4, 'sim', 'ok')"
            ),
            {"conversa": avaliada},
        )
    return cartoes, avaliada


def test_limpeza_tira_o_estado_do_canal_e_deixa_a_base_as_personas_e_as_reviews(usada):
    settings, avaliada = usada
    antes = contagens(settings)
    with conexao(settings) as con:
        apagadas = limpeza.limpar(con)
    depois = contagens(settings)
    for tabela in limpeza.APAGADAS:
        assert antes[tabela] > 0 and depois[tabela] == 0, tabela
    # A conversa avaliada fica, com os turnos, encerrada; as outras saem.
    assert (antes["app.conversas"], depois["app.conversas"]) == (2, 1)
    assert apagadas["app.conversas"] == 1 and depois["app.turnos"] == 1
    with conexao(settings) as con:
        assert con.execute(text("SELECT id, estado, contexto FROM app.conversas")).one() == (
            avaliada, "encerrada", {}
        )  # fmt: skip
    mantidas = {t: n for t, n in antes.items() if not t.startswith("app.")}
    mantidas |= {t: antes[t] for t in limpeza.MANTIDAS}
    assert {t: depois[t] for t in mantidas} == mantidas


def test_toda_tabela_do_canal_tem_destino_na_limpeza(usada):
    """Tabela nova no schema app precisa entrar na limpeza ou ficar de propósito: senão este teste
    falha, em vez de sobrar dado de teste na demo."""
    settings, _ = usada
    do_canal = {t for t in contagens(settings) if t.startswith("app.")}
    assert do_canal == {*limpeza.APAGADAS, *limpeza.MANTIDAS, "app.turnos", "app.conversas"}


def test_limpar_de_novo_nao_apaga_nada_e_as_referencias_nao_se_repetem(usada):
    settings, _ = usada
    with conexao(settings) as con:
        primeiro = con.execute(text("SELECT max(protocolo) FROM app.pre_casos")).scalar_one()
        limpeza.limpar(con)
    with conexao(settings) as con:
        assert set(limpeza.limpar(con).values()) == {0}
    with cliente(settings) as http:
        a = entrar(http, "CLI-A")
        conversa = abrir_conversa(http, a, "es")
        dizer(http, a, conversa, "No reconozco el cobro de 45,90 del 10/03")
        novo = dizer(http, a, conversa, "Sí, confirmo")["protocolo"]
    assert novo > primeiro
