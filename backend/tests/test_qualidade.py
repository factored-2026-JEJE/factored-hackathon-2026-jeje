"""Curadoria raw → curated: cada regra do contrato com um cenário construído à mão.

Os registros raw são inseridos direto no banco (texto, como vêm dos CSV); o esperado de cada teste
é o que a regra manda fazer com eles, não o que o código devolve.
"""

from datetime import datetime
from decimal import Decimal

import pytest
from conftest import conexao
from sqlalchemy import text

from jeje.dados.qualidade import curar

LINHA = iter(range(1, 10_000))


def raw(con, tabela: str, **valores) -> None:
    colunas = [*valores, "_arquivo", "_linha"]
    parametros = {**valores, "_arquivo": f"{tabela}.csv", "_linha": next(LINHA)}
    con.execute(
        text(
            f"insert into raw.{tabela} ({', '.join(colunas)}) "
            f"values ({', '.join(':' + c for c in colunas)})"
        ),
        parametros,
    )


def cliente(con, cid: str, **extra) -> None:
    raw(con, "customers", customer_id=cid, **extra)


def produto(con, pid: str, dono: str, **extra) -> None:
    campos = {"product_type": "Cuenta Ahorro", "currency": "USD", "product_status": "Active"}
    raw(con, "products", product_id=pid, customer_id=dono, **{**campos, **extra})


def transacao(con, tid: str, cliente_id: str, produto_id: str, **extra) -> None:
    campos = {
        "transaction_date": "2025-03-10 14:09:12", "amount": "189.77", "currency": "USD",
        "transaction_status": "Approved",
    }  # fmt: skip
    raw(con, "transactions", transaction_id=tid, customer_id=cliente_id, product_id=produto_id,
        **{**campos, **extra})  # fmt: skip


def curar_tudo(settings) -> dict:
    with conexao(settings) as con:
        cursor = con.connection.driver_connection.cursor()
        return curar(cursor, ["branches", "customers", "products", "transactions", "complaints"])


def quarentena(settings, tabela: str) -> dict[str, list[str]]:
    with conexao(settings) as con:
        linhas = con.execute(
            text("select registro, motivos from quality.quarentena where tabela = :t"),
            {"t": tabela},
        ).all()
    chave = {"transactions": "transaction_id", "customers": "customer_id"}.get(
        tabela, "complaint_id"
    )
    return {registro[chave]: sorted(motivos) for registro, motivos in linhas}


def um(settings, consulta: str):
    with conexao(settings) as con:
        return con.execute(text(consulta)).one()


@pytest.fixture
def base(banco_migrado):
    with conexao(banco_migrado) as con:
        cliente(con, "CLI-A")
        cliente(con, "CLI-B")
        produto(con, "PRD-A", "CLI-A")
        produto(con, "PRD-B", "CLI-B")
    return banco_migrado


def test_registro_valido_chega_tipado_a_curada(base):
    with conexao(base) as con:
        transacao(con, "TRX-1", "CLI-A", "PRD-A", is_fraud="False", response_code="00")
    curar_tudo(base)
    linha = um(base, "select amount, transaction_date, is_fraud, response_code "
                     "from curated.transactions where transaction_id = 'TRX-1'")  # fmt: skip
    assert linha == (Decimal("189.77"), datetime(2025, 3, 10, 14, 9, 12), False, "00")


def test_valor_nao_conversivel_vai_para_quarentena_com_o_original(base):
    with conexao(base) as con:
        transacao(con, "TRX-2", "CLI-A", "PRD-A", amount="12,50")
    resumo = curar_tudo(base)["transactions"]
    assert quarentena(base, "transactions") == {"TRX-2": ["Q-TIPO:amount"]}
    registro = um(base, "select registro->>'amount' from quality.quarentena")[0]
    assert registro == "12,50"
    assert (resumo.curado, resumo.quarentena) == (0, 1)


def test_obrigatorio_vazio_e_dominio_invalido_acumulam_motivos(base):
    with conexao(base) as con:
        transacao(con, "TRX-3", "CLI-A", "PRD-A", transaction_status="Aprobada", currency=None)
    curar_tudo(base)
    assert quarentena(base, "transactions") == {
        "TRX-3": ["Q-DOMINIO:transaction_status", "Q-OBRIG:currency"]
    }


def test_referencia_essencial_inexistente_vai_para_quarentena(base):
    with conexao(base) as con:
        transacao(con, "TRX-4", "CLI-Z", "PRD-A")
    curar_tudo(base)
    assert quarentena(base, "transactions") == {"TRX-4": ["Q-PROP:product_id", "Q-REF:customer_id"]}


def test_transacao_com_produto_de_outro_cliente_vai_para_quarentena(base):
    with conexao(base) as con:
        transacao(con, "TRX-5", "CLI-B", "PRD-A")
        transacao(con, "TRX-6", "CLI-B", "PRD-B")
    resumo = curar_tudo(base)["transactions"]
    assert quarentena(base, "transactions") == {"TRX-5": ["Q-PROP:product_id"]}
    assert resumo.curado == 1


def test_referencia_acessoria_inexistente_e_anulada_sem_perder_o_registro(base):
    with conexao(base) as con:
        cliente(con, "CLI-C", registration_branch_id="SUC-INEXISTENTE")
    resumo = curar_tudo(base)["customers"]
    assert um(base, "select registration_branch_id from curated.customers "
                    "where customer_id = 'CLI-C'") == (None,)  # fmt: skip
    assert resumo.anulacoes == {"A-REF:registration_branch_id": 1}
    assert resumo.quarentena == 0


def test_reclamacao_nunca_fica_ligada_a_produto_de_outro_cliente(base):
    with conexao(base) as con:
        raw(
            con,
            "complaints",
            complaint_id="CMP-1",
            creation_date="2025-03-10 20:34:30",
            customer_id="CLI-B",
            case_type="Claim",
            status="Open",
            affected_product_id="PRD-A",
        )
        raw(
            con,
            "complaints",
            complaint_id="CMP-2",
            creation_date="2025-03-10 20:35:00",
            customer_id="CLI-B",
            case_type="Claim",
            status="Open",
            affected_product_id="PRD-B",
        )
    resumo = curar_tudo(base)["complaints"]
    with conexao(base) as con:
        ligados = dict(
            con.execute(
                text("select complaint_id, affected_product_id from curated.complaints")
            ).all()
        )
    assert ligados == {"CMP-1": None, "CMP-2": "PRD-B"}
    assert resumo.anulacoes["A-PROP:affected_product_id"] == 1


def test_copia_exata_fica_uma_so_e_e_contada(base):
    with conexao(base) as con:
        transacao(con, "TRX-7", "CLI-A", "PRD-A")
        transacao(con, "TRX-7", "CLI-A", "PRD-A")
    resumo = curar_tudo(base)["transactions"]
    assert (resumo.curado, resumo.copias_descartadas, resumo.quarentena) == (1, 1, 0)


def test_chave_repetida_com_conteudo_diferente_nao_e_escolhida_em_silencio(base):
    with conexao(base) as con:
        transacao(con, "TRX-8", "CLI-A", "PRD-A", amount="10.00")
        transacao(con, "TRX-8", "CLI-A", "PRD-A", amount="99.00")
    resumo = curar_tudo(base)["transactions"]
    assert (resumo.curado, resumo.quarentena) == (0, 2)
    assert resumo.motivos == {"Q-PK-CONFLITO": 2}


def test_amount_usd_de_transacao_em_dolar_e_normalizado_e_as_demais_nao(base):
    with conexao(base) as con:
        transacao(con, "TRX-9", "CLI-A", "PRD-A", currency="USD", amount="50.00")
        transacao(con, "TRX-10", "CLI-A", "PRD-A", currency="COP", amount="200000.00")
    resumo = curar_tudo(base)["transactions"]
    with conexao(base) as con:
        usd = dict(
            con.execute(text("select transaction_id, amount_usd from curated.transactions")).all()
        )
    assert usd == {"TRX-9": Decimal("50.00"), "TRX-10": None}
    assert resumo.normalizacoes == {"N-USD:amount_usd": 1}


def test_filho_de_registro_em_quarentena_tambem_vai_para_quarentena(base):
    with conexao(base) as con:
        cliente(con, "CLI-D", document_type="Cédula")
        produto(con, "PRD-D", "CLI-D")
        transacao(con, "TRX-11", "CLI-D", "PRD-D")
    resumos = curar_tudo(base)
    assert quarentena(base, "customers") == {"CLI-D": ["Q-DOMINIO:document_type"]}
    assert resumos["products"].quarentena == 1
    assert quarentena(base, "transactions") == {
        "TRX-11": [
            "Q-REF:customer_id",
            "Q-REF:product_id",
        ]  # produto do cliente em quarentena também ficou fora
    }


def test_relatorio_fecha_raw_igual_a_curado_mais_quarentena_mais_copias(base):
    with conexao(base) as con:
        transacao(con, "TRX-12", "CLI-A", "PRD-A")
        transacao(con, "TRX-12", "CLI-A", "PRD-A")
        transacao(con, "TRX-13", "CLI-A", "PRD-A", amount="x")
    curar_tudo(base)
    with conexao(base) as con:
        linhas = con.execute(
            text(
                "select tabela, raw, curado, quarentena, copias_descartadas from quality.relatorio"
            )
        ).all()
    por_tabela = {t: (r, c, q, d) for t, r, c, q, d in linhas}
    assert por_tabela["transactions"] == (3, 1, 1, 1)
    assert por_tabela["customers"] == (2, 2, 0, 0)
    assert all(r == c + q + d for r, c, q, d in por_tabela.values())
