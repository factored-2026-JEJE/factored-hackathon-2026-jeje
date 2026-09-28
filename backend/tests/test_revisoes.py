"""Revisões e ordem de chegada (DEV-004): a versão mais recente por process_date vence, empate é
conflito, e o resultado não depende da ordem em que os registros chegaram."""

from decimal import Decimal

from conftest import conexao
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from test_qualidade import base, cliente, curar_tudo, quarentena, transacao

__all__ = ["base"]  # fixture importada da suíte de qualidade


def curadas(settings) -> dict[str, Decimal]:
    with conexao(settings) as con:
        return dict(
            con.execute(text("select transaction_id, amount from curated.transactions")).all()
        )


def test_revisao_mais_recente_substitui_a_anterior(base):
    with conexao(base) as con:
        transacao(con, "TRX-1", "CLI-A", "PRD-A", process_date="2025-03-10", amount="10.00")
        transacao(con, "TRX-1", "CLI-A", "PRD-A", process_date="2025-03-12", amount="12.00")
    resumo = curar_tudo(base)["transactions"]
    assert curadas(base) == {"TRX-1": Decimal("12.00")}
    assert resumo.motivos == {"R-REVISAO-SUBSTITUIDA": 1}
    with conexao(base) as con:
        antiga = con.execute(text("select registro->>'amount' from quality.quarentena")).one()
    assert antiga == ("10.00",)


def test_empate_na_data_mais_recente_e_conflito(base):
    with conexao(base) as con:
        transacao(con, "TRX-2", "CLI-A", "PRD-A", process_date="2025-03-10", amount="1.00")
        transacao(con, "TRX-2", "CLI-A", "PRD-A", process_date="2025-03-11", amount="2.00")
        transacao(con, "TRX-2", "CLI-A", "PRD-A", process_date="2025-03-11", amount="3.00")
    resumo = curar_tudo(base)["transactions"]
    assert curadas(base) == {}
    assert resumo.motivos == {"R-REVISAO-SUBSTITUIDA": 1, "Q-PK-CONFLITO": 2}


def test_revisao_com_copia_exata_da_versao_nova(base):
    with conexao(base) as con:
        transacao(con, "TRX-3", "CLI-A", "PRD-A", process_date="2025-03-10", amount="5.00")
        transacao(con, "TRX-3", "CLI-A", "PRD-A", process_date="2025-03-11", amount="6.00")
        transacao(con, "TRX-3", "CLI-A", "PRD-A", process_date="2025-03-11", amount="6.00")
    resumo = curar_tudo(base)["transactions"]
    assert curadas(base) == {"TRX-3": Decimal("6.00")}
    assert (resumo.quarentena, resumo.copias_descartadas) == (1, 1)


def test_tabela_sem_process_date_nao_tem_revisao_so_conflito(base):
    with conexao(base) as con:
        cliente(con, "CLI-C", segment="Basic")
        cliente(con, "CLI-C", segment="Plus")
    curar_tudo(base)
    assert quarentena(base, "customers") == {"CLI-C": ["Q-PK-CONFLITO"]}


def test_versao_com_data_invalida_nao_substitui_nem_e_substituida(base):
    with conexao(base) as con:
        transacao(con, "TRX-4", "CLI-A", "PRD-A", process_date="2025-03-10", amount="7.00")
        transacao(con, "TRX-4", "CLI-A", "PRD-A", process_date="2025-03-12", amount="9.00")
        transacao(con, "TRX-4", "CLI-A", "PRD-A", process_date="amanhã", amount="8.00")
    curar_tudo(base)
    assert curadas(base) == {"TRX-4": Decimal("9.00")}
    with conexao(base) as con:
        motivos = dict(
            con.execute(text("select registro->>'amount', motivos from quality.quarentena")).all()
        )
    assert motivos == {"7.00": ["R-REVISAO-SUBSTITUIDA"], "8.00": ["Q-TIPO:process_date"]}


# ---- Propriedade: ordem de chegada irrelevante ------------------------------------------------

DIAS = ("2025-03-10", "2025-03-11", "2025-03-12")
VALORES = ("1.00", "2.00", "3.00")
VERSOES = st.lists(st.tuples(st.sampled_from(("TRX-P1", "TRX-P2")), st.sampled_from(DIAS),
                             st.sampled_from(VALORES)), min_size=1, max_size=8)  # fmt: skip


def oraculo(versoes: list[tuple[str, str, str]]) -> dict[str, Decimal]:
    """Regra escrita à parte: conteúdo único vence; senão, o único conteúdo da data mais recente."""
    esperado = {}
    for chave in {v[0] for v in versoes}:
        proprias = {(dia, valor) for c, dia, valor in versoes if c == chave}
        if len({valor for _, valor in proprias}) == 1 and len(proprias) == 1:
            esperado[chave] = Decimal(next(iter(proprias))[1])
            continue
        recente = max(dia for dia, _ in proprias)
        finais = {valor for dia, valor in proprias if dia == recente}
        if len(finais) == 1:
            esperado[chave] = Decimal(finais.pop())
    return esperado


@settings(max_examples=40, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])  # fmt: skip
@given(versoes=VERSOES, ordem=st.randoms(use_true_random=False))
@example(versoes=[("TRX-P1", "2025-03-12", "3.00"), ("TRX-P1", "2025-03-10", "1.00")],
         ordem=__import__("random").Random(0))  # fmt: skip
def test_resultado_nao_depende_da_ordem_de_chegada(base, versoes, ordem):
    embaralhadas = list(versoes)
    ordem.shuffle(embaralhadas)
    with conexao(base) as con:
        con.execute(text("truncate raw.transactions"))
        for chave, dia, valor in embaralhadas:
            transacao(con, chave, "CLI-A", "PRD-A", process_date=dia, amount=valor)
    curar_tudo(base)
    assert curadas(base) == oraculo(versoes)
