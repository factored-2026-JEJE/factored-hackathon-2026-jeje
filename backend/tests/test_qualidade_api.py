"""Rota do relatório de qualidade contra uma carga real da fixture de defeitos conhecidos."""

from conftest import cliente
from test_carga import escrever_csv

from jeje.dados import manifesto
from jeje.dados.carga import carregar


def test_relatorio_mostra_a_curadoria_da_ultima_carga_na_ordem_dos_contratos(
    banco_migrado, tmp_path
):
    raiz, manifestos = tmp_path / "raw", tmp_path / "manifesto"
    escrever_csv(raiz, "customers.csv", "customers", [
        {"customer_id": "CLI-A", "registration_branch_id": "SUC-INEXISTENTE"},
        {"customer_id": "CLI-B", "document_type": "Cédula"},
    ])  # fmt: skip
    escrever_csv(raiz, "branches.csv", "branches", [{"branch_id": "SUC-1"}])
    escrever_csv(raiz, "daily_exchange_rates.csv", "daily_exchange_rates", [
        {"date": "2025-03-10", "source_currency": "COP", "target_currency": "USD",
         "exchange_rate": "0.000242"},
    ])  # fmt: skip
    tabelas = ["customers", "branches", "daily_exchange_rates"]
    manifesto.escrever(manifestos, manifesto.gerar(raiz, tabelas))
    carregar(banco_migrado, raiz, manifestos, tabelas, "fixture", "p1")

    with cliente(banco_migrado) as http:
        resposta = http.get("/dados/qualidade")
    assert resposta.status_code == 200
    assert resposta.json() == [
        {"tabela": "branches", "raw": 1, "curado": 1, "quarentena": 0, "copias_descartadas": 0,
         "motivos": {}, "anulacoes": {}, "normalizacoes": {}},
        {"tabela": "daily_exchange_rates", "raw": 1, "curado": 1, "quarentena": 0,
         "copias_descartadas": 0, "motivos": {}, "anulacoes": {}, "normalizacoes": {}},
        {"tabela": "customers", "raw": 2, "curado": 1, "quarentena": 1, "copias_descartadas": 0,
         "motivos": {"Q-DOMINIO:document_type": 1},
         "anulacoes": {"A-REF:registration_branch_id": 1}, "normalizacoes": {}},
    ]  # fmt: skip


def test_sem_carga_o_relatorio_e_vazio(banco_migrado):
    with cliente(banco_migrado) as http:
        assert http.get("/dados/qualidade").json() == []
