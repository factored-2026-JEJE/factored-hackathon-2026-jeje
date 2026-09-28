"""Personas e sessões contra o PostgreSQL real (identidade só pela sessão provisionada)."""

import pytest
from conftest import conexao
from sqlalchemy import text
from test_qualidade import base, cliente, curar_tudo, produto, transacao

from jeje import sessao

__all__ = ["base"]  # fixture importada da suíte de qualidade


@pytest.fixture
def curada(base):
    with conexao(base) as con:
        cliente(con, "CLI-C", first_name="Ana", last_name="Souza")
        produto(con, "PRD-C", "CLI-C")
        transacao(con, "TRX-A1", "CLI-A", "PRD-A")
        transacao(con, "TRX-A2", "CLI-A", "PRD-A", transaction_status="Declined")
        transacao(con, "TRX-C1", "CLI-C", "PRD-C")
        transacao(con, "TRX-C2", "CLI-C", "PRD-C", transaction_status="Pending")
        transacao(con, "TRX-B1", "CLI-B", "PRD-B")
    curar_tudo(base)
    return base


def personas(settings) -> list[tuple]:
    with conexao(settings) as con:
        return [
            tuple(r)
            for r in con.execute(
                text("select customer_id, nome, ordem from app.personas order by ordem")
            )
        ]


def test_personas_sao_os_clientes_com_mais_variedade_de_status_em_ordem_estavel(curada):
    with conexao(curada) as con:
        assert sessao.provisionar_personas(con, 2) == ["CLI-A", "CLI-C"]
    assert personas(curada) == [("CLI-A", "CLI-A", 1), ("CLI-C", "Ana Souza", 2)]


def test_reprovisionar_nao_duplica_e_respeita_a_quantidade(curada):
    with conexao(curada) as con:
        sessao.provisionar_personas(con, 5)
        sessao.provisionar_personas(con, 5)
    assert [p[0] for p in personas(curada)] == ["CLI-A", "CLI-C", "CLI-B"]


def test_sessao_so_abre_para_persona_e_valida_pelo_token(curada):
    with conexao(curada) as con:
        sessao.provisionar_personas(con, 1)
        token, _ = sessao.abrir(con, "CLI-A", 60)
        with pytest.raises(sessao.PersonaDesconhecida):
            sessao.abrir(con, "CLI-B", 60)
        assert len(token) >= 43  # 32 bytes aleatórios em base64url
        assert sessao.validar(con, token) == sessao.SessaoAtiva(customer_id="CLI-A")
        assert sessao.validar(con, token + "x") is None


def test_banco_guarda_so_o_hash_do_token(curada):
    with conexao(curada) as con:
        sessao.provisionar_personas(con, 1)
        token, _ = sessao.abrir(con, "CLI-A", 60)
        guardado = con.execute(text("select token_hash from app.sessoes")).scalar_one()
    assert token not in guardado
    assert guardado == sessao.hash_token(token) and len(guardado) == 64


def test_sessao_expirada_nao_vale(curada):
    with conexao(curada) as con:
        sessao.provisionar_personas(con, 1)
        token, expira_em = sessao.abrir(con, "CLI-A", 60)
        agora = con.execute(text("select now()")).scalar_one()
        assert 59 * 60 <= (expira_em - agora).total_seconds() <= 60 * 60
        con.execute(text("update app.sessoes set expira_em = now() - interval '1 second'"))
        assert sessao.validar(con, token) is None
