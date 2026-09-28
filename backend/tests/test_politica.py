"""Política determinística: cada regra da matriz (DEV-006) com o caso que deve e o que não deve
valer. Funções puras: o esperado vem da matriz, não do código."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jeje.politica import (
    STATUS_CONHECIDOS,
    Candidata,
    Decisao,
    Fatos,
    Pista,
    decidir_consulta,
    decidir_contestacao,
    decidir_esclarecimento,
    decidir_pedido,
    resolver_transacao,
)

LIMITE = Decimal("1000.00")


def fatos(status: str = "Approved", codigo: str | None = None, usd: str | None = "50.00") -> Fatos:
    return Fatos("TRX-1", status, codigo, None if usd is None else Decimal(usd))


@pytest.mark.parametrize(
    ("status", "codigo", "esperado"),
    [
        ("Approved", None, Decisao("POL-CON-01", "responder")),
        ("Declined", "51", Decisao("POL-CON-03", "responder", "51")),
        ("Declined", None, Decisao("POL-CON-04", "responder")),
        ("Declined", "99", Decisao("POL-CON-04", "responder")),
        ("Pending", None, Decisao("POL-CON-05", "responder", "Pending")),
        ("Reversed", "05", Decisao("POL-CON-05", "responder", "Reversed")),
        ("Chargeback", None, Decisao("POL-CON-04", "humano", "status desconhecido")),
    ],
)
def test_consulta_segue_a_matriz_por_status_e_codigo(status, codigo, esperado):
    assert decidir_consulta(fatos(status, codigo)) == esperado


def test_contestacao_de_aprovada_dentro_do_limite_propoe_pre_caso():
    assert decidir_contestacao(fatos(), LIMITE, None) == Decisao("POL-DISP-01", "propor_pre_caso")


def test_contestacao_no_limite_exato_ainda_propoe_e_um_centavo_acima_nao():
    assert decidir_contestacao(fatos(usd="1000.00"), LIMITE, None).acao == "propor_pre_caso"
    assert decidir_contestacao(fatos(usd="1000.01"), LIMITE, None) == Decisao(
        "POL-HUM-02", "humano", "acima do limite simulado"
    )


@pytest.mark.parametrize("status", ["Declined", "Pending", "Reversed"])
def test_contestacao_de_transacao_nao_aprovada_vai_para_humano_sem_pre_caso(status):
    """ACH-001: recusa não vira disputa em silêncio."""
    assert decidir_contestacao(fatos(status), LIMITE, None) == Decisao(
        "POL-DISP-02", "humano", status
    )


def test_contestacao_sem_valor_em_usd_vai_para_humano():
    assert decidir_contestacao(fatos(usd=None), LIMITE, None) == Decisao(
        "POL-HUM-02", "humano", "valor em USD indisponível"
    )


def test_pre_caso_existente_devolve_o_protocolo_sem_propor_outro():
    assert decidir_contestacao(fatos(), LIMITE, "PC-000123") == Decisao(
        "POL-DISP-03", "responder", "PC-000123"
    )


@given(
    status=st.sampled_from(sorted(STATUS_CONHECIDOS | {"Chargeback"})),
    valor=st.none() | st.decimals(min_value=0, max_value=10**7, places=2),
    existente=st.none() | st.text(min_size=1, max_size=12),
)
def test_propriedade_so_propoe_pre_caso_quando_toda_a_regra_permite(status, valor, existente):
    decisao = decidir_contestacao(Fatos("T", status, None, valor), LIMITE, existente)
    assert decisao.regra.startswith("POL-")
    if decisao.acao == "propor_pre_caso":
        assert status == "Approved" and valor is not None and valor <= LIMITE
        assert existente is None


# ---- Desambiguação ------------------------------------------------------------------------------

CANDIDATAS = [
    Candidata("T1", Decimal("189.77"), datetime(2025, 3, 10, 14, 9), "Almacenes Éxito"),
    Candidata("T2", Decimal("50.00"), datetime(2025, 3, 10, 18, 0), "Farmacia San Jorge"),
    Candidata("T3", Decimal("189.77"), datetime(2025, 3, 12, 9, 0), "Éxito Express"),
]


@pytest.mark.parametrize(
    ("pista", "tipo", "ids"),
    [
        (Pista(valor=Decimal("50")), "unica", ("T2",)),
        (Pista(valor=Decimal("189.77")), "varias", ("T1", "T3")),
        (Pista(valor=Decimal("189.77"), data=date(2025, 3, 12)), "unica", ("T3",)),
        (Pista(comercio="exito"), "varias", ("T1", "T3")),
        (Pista(comercio="ÉXITO EXPRESS"), "unica", ("T3",)),
        (Pista(valor=Decimal("999")), "nenhuma", ()),
        (Pista(valor=Decimal("189.00")), "nenhuma", ()),
    ],
    ids=[
        "valor-unico",
        "valor-repetido",
        "valor-e-data",
        "comercio-sem-acento",
        "comercio-exato",
        "nada-casa",
        "valor-aproximado-nao-casa",
    ],
)
def test_desambiguacao_nunca_escolhe_entre_varias(pista, tipo, ids):
    resolucao = resolver_transacao(CANDIDATAS, pista)
    assert (resolucao.tipo, resolucao.transacoes, resolucao.regra) == (tipo, ids, "POL-CON-02")


def test_sem_pista_lista_no_maximo_o_limite_de_opcoes_na_ordem_recebida():
    muitas = [
        Candidata(f"T{i}", Decimal(i), datetime(2025, 3, 1, 10, 0), "Loja") for i in range(1, 8)
    ]
    assert resolver_transacao(muitas, Pista(), maximo_opcoes=5).transacoes == (
        "T1", "T2", "T3", "T4", "T5",
    )  # fmt: skip


@pytest.mark.parametrize(
    ("intencao", "id_digitado", "esperado"),
    [
        ("fraude", False, Decisao("POL-HUM-01", "humano", "relato de fraude")),
        ("fraude", True, Decisao("POL-HUM-01", "humano", "relato de fraude")),
        ("humano", False, Decisao("POL-HUM-03", "humano", "pedido explícito")),
        ("fora_de_escopo", False, Decisao("POL-ESC-01", "recusar")),
        ("contestar", True, Decisao("POL-ID-02", "recusar", "identificador digitado")),
        ("consultar", True, Decisao("POL-ID-02", "recusar", "identificador digitado")),
        ("contestar", False, None),
        ("consultar", False, None),
        ("desconhecida", False, None),
    ],
)
def test_pedido_segue_a_matriz_com_seguranca_primeiro(intencao, id_digitado, esperado):
    assert decidir_pedido(intencao, id_digitado) == esperado


def test_dois_esclarecimentos_sem_sucesso_levam_ao_humano():
    assert decidir_esclarecimento(0) == Decisao("POL-CON-02", "esclarecer")
    assert decidir_esclarecimento(1) == Decisao("POL-CON-02", "esclarecer")
    assert decidir_esclarecimento(2) == Decisao(
        "POL-HUM-03", "humano", "esclarecimentos sem sucesso"
    )
