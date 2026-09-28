"""Coerência dos contratos com a camada raw e entre si (erros de declaração pegos cedo)."""

import pytest

from jeje.dados.contratos import CONTRATOS, TIPOS, Contrato, Referencia, colunas
from jeje.dados.raw import COLUNAS


@pytest.mark.parametrize("contrato", CONTRATOS, ids=lambda c: c.tabela)
def test_contrato_so_cita_colunas_e_tipos_existentes(contrato: Contrato):
    existentes = set(COLUNAS[contrato.tabela])
    citadas = (
        set(contrato.chave) | set(contrato.tipos) | set(contrato.obrigatorias)
        | set(contrato.dominios) | {r.coluna for r in contrato.referencias}
    )  # fmt: skip
    assert citadas <= existentes, citadas - existentes
    assert set(contrato.tipos.values()) <= set(TIPOS)
    assert all(valores for valores in contrato.dominios.values())


def test_referencias_apontam_para_tabelas_anteriores_com_chave_simples():
    vistas: dict[str, Contrato] = {}
    for contrato in CONTRATOS:
        for referencia in contrato.referencias:
            alvo = vistas.get(referencia.tabela)
            assert alvo is not None, f"{contrato.tabela}.{referencia.coluna} → {referencia.tabela}"
            assert len(alvo.chave) == 1
            if referencia.mesmo_cliente:
                assert "customer_id" in COLUNAS[alvo.tabela]
                assert "customer_id" in COLUNAS[contrato.tabela]
        vistas[contrato.tabela] = contrato


def test_politica_das_referencias_que_protegem_o_cliente():
    """Transação→produto é essencial e exige o mesmo cliente; reclamação→produto nunca liga
    produto de terceiro (ACH-016); agência de cadastro quebrada não derruba o cliente (ACH-017)."""
    por_coluna = {
        (c.tabela, r.coluna): r for c in CONTRATOS for r in c.referencias
    }  # fmt: skip
    assert por_coluna["transactions", "product_id"] == Referencia(
        "product_id", "products", essencial=True, mesmo_cliente=True
    )
    assert por_coluna["complaints", "affected_product_id"].mesmo_cliente
    assert not por_coluna["customers", "registration_branch_id"].essencial


def test_colunas_curadas_sao_as_da_raw_na_mesma_ordem():
    for contrato in CONTRATOS:
        assert colunas(contrato) == COLUNAS[contrato.tabela]
