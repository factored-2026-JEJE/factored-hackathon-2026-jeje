"""Política determinística: cada regra da matriz (DEV-006) com o caso que deve e o que não deve
valer. Funções puras: o esperado vem da matriz, não do código."""

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from jeje.politica import (
    STATUS_CONHECIDOS,
    Candidata,
    Cartao,
    Decisao,
    Fatos,
    Limites,
    Pista,
    bloqueaveis,
    decidir_bloqueio,
    decidir_consulta,
    decidir_contestacao,
    decidir_esclarecimento,
    decidir_pedido,
    decidir_status_do_caso,
    noturna_digital,
    resolver_transacao,
)

# Limites do próprio teste (não os do compose): números diferentes para cada regra.
LIMITES = Limites(
    padrao_usd=Decimal("1000.00"),
    noturno_usd=Decimal("200.00"),
    noturno_dia_usd=Decimal("500.00"),
    noturno_inicio_h=20,
    noturno_fim_h=6,
    canais_digitais=frozenset({"App", "Web"}),
    seguranca_transferencia_usd=Decimal("50000.00"),
    janela_contestacao_dias=120,
    reincidencia_pre_casos=3,
    reincidencia_dias=30,
)
LIMITE = LIMITES.padrao_usd


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
    assert decidir_consulta(fatos(status, codigo), LIMITES) == esperado


def test_contestacao_de_aprovada_dentro_do_limite_propoe_pre_caso():
    assert decidir_contestacao(fatos(), LIMITES, None) == Decisao("POL-DISP-01", "propor_pre_caso")


def test_contestacao_no_limite_exato_ainda_propoe_e_um_centavo_acima_nao():
    assert decidir_contestacao(fatos(usd="1000.00"), LIMITES, None).acao == "propor_pre_caso"
    assert decidir_contestacao(fatos(usd="1000.01"), LIMITES, None) == Decisao(
        "POL-HUM-02", "humano", "acima do limite simulado"
    )


@pytest.mark.parametrize("status", ["Declined", "Pending", "Reversed"])
def test_contestacao_de_transacao_nao_aprovada_vai_para_humano_sem_pre_caso(status):
    """ACH-001: recusa não vira disputa em silêncio."""
    assert decidir_contestacao(fatos(status), LIMITES, None) == Decisao(
        "POL-DISP-02", "humano", status
    )


def test_contestacao_sem_valor_em_usd_vai_para_humano():
    assert decidir_contestacao(fatos(usd=None), LIMITES, None) == Decisao(
        "POL-HUM-02", "humano", "valor em USD indisponível"
    )


def test_pre_caso_existente_devolve_o_protocolo_sem_propor_outro():
    assert decidir_contestacao(fatos(), LIMITES, "PC-000123") == Decisao(
        "POL-DISP-03", "responder", "PC-000123"
    )


@given(
    status=st.sampled_from(sorted(STATUS_CONHECIDOS | {"Chargeback"})),
    valor=st.none() | st.decimals(min_value=0, max_value=10**7, places=2),
    existente=st.none() | st.text(min_size=1, max_size=12),
)
# Caso que a busca aleatória pode não sortear: tudo permitiria, menos o pré-caso já aberto.
@example(status="Approved", valor=Decimal("50.00"), existente="PC-1")
def test_propriedade_so_propoe_pre_caso_quando_toda_a_regra_permite(status, valor, existente):
    decisao = decidir_contestacao(Fatos("T", status, None, valor), LIMITES, existente)
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


def test_a_ultima_escolhe_a_mais_recente_das_que_casam():
    """As candidatas chegam mais recentes primeiro; "a última" é o critério do cliente."""
    candidatas = [
        Candidata("T3", Decimal("20.00"), datetime(2025, 3, 14), "Uber"),
        Candidata("T2", Decimal("45.90"), datetime(2025, 3, 12), "Cine Premium"),
        Candidata("T1", Decimal("45.90"), datetime(2025, 3, 10), "Streaming Plus"),
    ]
    assert resolver_transacao(candidatas, Pista(ultima=True)).transacoes == ("T3",)
    assert resolver_transacao(candidatas, Pista(Decimal("45.90"), ultima=True)).transacoes == (
        "T2",
    )
    assert resolver_transacao(candidatas, Pista(Decimal("45.90"))).tipo == "varias"
    assert resolver_transacao(candidatas, Pista(Decimal("9.99"), ultima=True)).tipo == "nenhuma"


def test_status_do_caso_responde_sem_encaminhar_e_distingue_nenhum_um_e_varios():
    assert decidir_status_do_caso(0) == Decisao(
        "POL-CASO-03", "responder", "nenhum pré-caso do cliente"
    )
    assert decidir_status_do_caso(1) == Decisao("POL-CASO-01", "responder")
    assert decidir_status_do_caso(2) == Decisao("POL-CASO-02", "responder")


def test_dois_esclarecimentos_sem_sucesso_oferecem_o_humano():
    assert decidir_esclarecimento(0) == Decisao("POL-CON-02", "esclarecer")
    assert decidir_esclarecimento(1) == Decisao("POL-CON-02", "esclarecer")
    assert decidir_esclarecimento(2) == Decisao(
        "POL-HUM-03", "oferecer_humano", "esclarecimentos sem sucesso"
    )


# ---- Limites por horário, canal e tipo (PRD-001) ------------------------------------------------


def em(hora: str, canal: str | None = "App", usd: str = "150.00", tipo: str = "Purchase",
       status: str = "Approved") -> Fatos:  # fmt: skip
    return Fatos(
        "TRX-N", status, None, Decimal(usd), tipo, canal,
        datetime.fromisoformat(f"2025-03-10T{hora}"),
    )  # fmt: skip


@pytest.mark.parametrize(
    ("hora", "canal", "noturna"),
    [
        ("20:00:00", "App", True), ("19:59:59", "App", False), ("05:59:59", "Web", True),
        ("06:00:00", "Web", False), ("23:30:00", "POS", False), ("02:00:00", "ATM", False),
        ("03:00:00", None, False),
    ],
)  # fmt: skip
def test_noturna_digital_pelo_horario_e_pelo_canal(hora, canal, noturna):
    assert noturna_digital(em(hora, canal), LIMITES) is noturna


def test_sem_data_ou_com_janela_no_mesmo_dia():
    assert (
        noturna_digital(Fatos("T", "Approved", None, Decimal("10"), None, "App"), LIMITES) is False
    )
    madrugada = Limites(**{**LIMITES.__dict__, "noturno_inicio_h": 1, "noturno_fim_h": 5})
    assert noturna_digital(em("03:00:00"), madrugada) is True
    assert noturna_digital(em("23:00:00"), madrugada) is False


@pytest.mark.parametrize(
    ("usd", "no_dia", "esperado"),
    [
        ("200.00", "0", Decisao("POL-DISP-01", "propor_pre_caso")),
        ("200.01", "0",
         Decisao("POL-HUM-04", "humano", "noturna digital acima do limite por transação")),
        ("100.00", "400.00", Decisao("POL-DISP-01", "propor_pre_caso")),
        ("100.01", "400.00",
         Decisao("POL-HUM-04", "humano", "noturna digital acima do limite do dia")),
    ],
)  # fmt: skip
def test_noturna_digital_tem_limite_por_transacao_e_por_dia(usd, no_dia, esperado):
    assert (
        decidir_contestacao(em("22:00:00", "Web", usd), LIMITES, None, Decimal(no_dia)) == esperado
    )


def test_de_dia_ou_em_canal_fisico_vale_so_o_limite_padrao():
    ja_no_dia = Decimal("400")
    assert decidir_contestacao(em("14:00:00", "App", "900.00"), LIMITES, None, ja_no_dia).regra == (
        "POL-DISP-01"
    )
    assert decidir_contestacao(em("22:00:00", "POS", "900.00"), LIMITES, None, ja_no_dia).regra == (
        "POL-DISP-01"
    )
    assert decidir_contestacao(em("22:00:00", "POS", "1000.01"), LIMITES, None).regra == (
        "POL-HUM-02"
    )


@pytest.mark.parametrize(
    ("tipo", "usd", "status", "regra"),
    [
        ("Transfer", "50000.01", "Approved", "POL-SEG-01"),
        ("Transfer", "50000.00", "Approved", "POL-HUM-02"),  # no limite: não é atípica
        ("Transfer", "60000.00", "Declined", "POL-SEG-01"),  # segurança antes do status
        ("Payment", "60000.00", "Approved", "POL-HUM-02"),  # só transferência
    ],
)
def test_transferencia_atipica_vai_para_seguranca_na_contestacao(tipo, usd, status, regra):
    fatos = em("11:00:00", "Web", usd, tipo, status)
    assert decidir_contestacao(fatos, LIMITES, None).regra == regra


def test_transferencia_atipica_vai_para_seguranca_tambem_na_consulta():
    atipica = em("11:00:00", "Web", "60000.00", "Transfer", "Declined")
    assert decidir_consulta(atipica, LIMITES) == Decisao(
        "POL-SEG-01", "humano", "transferência acima do limite de segurança"
    )
    assert decidir_consulta(em("11:00:00", "Web", "60000.00", "Payment"), LIMITES).regra == (
        "POL-CON-01"
    )


# ---- Janela e reincidência (PRD-008) ------------------------------------------------------------

HOJE = date(2025, 3, 10)  # o "hoje" dos dados: o último dia da base, não o relógio


def comprada(dias_atras: int, usd: str = "50.00") -> Fatos:
    quando = datetime.combine(HOJE - timedelta(days=dias_atras), time(14))
    return Fatos("TRX-1", "Approved", None, Decimal(usd), transaction_date=quando)


@pytest.mark.parametrize(
    ("dias", "regra"), [(0, "POL-DISP-01"), (120, "POL-DISP-01"), (121, "POL-HUM-05")]
)
def test_janela_de_contestacao_conta_do_hoje_dos_dados(dias, regra):
    decisao = decidir_contestacao(comprada(dias), LIMITES, None, hoje=HOJE)
    assert decisao.regra == regra
    assert decisao.acao == ("humano" if regra == "POL-HUM-05" else "propor_pre_caso")


@pytest.mark.parametrize(
    ("recentes", "regra"), [(0, "POL-DISP-01"), (2, "POL-DISP-01"), (3, "POL-HUM-06")]
)
def test_reincidencia_manda_a_proxima_contestacao_para_o_atendente(recentes, regra):
    decisao = decidir_contestacao(
        comprada(1), LIMITES, None, hoje=HOJE, pre_casos_recentes=recentes
    )
    assert decisao.regra == regra


def test_ordem_das_regras_com_janela_e_reincidencia():
    """Pré-caso existente e transação não aprovada vêm antes da janela; a janela vem antes da
    reincidência, e as duas antes do limite de valor (a compra antiga de USD 9.999 é da janela)."""
    antiga_e_cara = comprada(200, usd="9999.00")
    assert decidir_contestacao(antiga_e_cara, LIMITES, "PC-1", hoje=HOJE).regra == "POL-DISP-03"
    nao_aprovada = replace(antiga_e_cara, status="Declined")
    assert decidir_contestacao(nao_aprovada, LIMITES, None, hoje=HOJE).regra == "POL-DISP-02"
    assert (
        decidir_contestacao(antiga_e_cara, LIMITES, None, hoje=HOJE, pre_casos_recentes=5).regra
        == "POL-HUM-05"
    )
    recente_e_cara = comprada(1, usd="9999.00")
    assert (
        decidir_contestacao(recente_e_cara, LIMITES, None, hoje=HOJE, pre_casos_recentes=5).regra
        == "POL-HUM-06"
    )
    assert decidir_contestacao(recente_e_cara, LIMITES, None, hoje=HOJE).regra == "POL-HUM-02"


# ---- Bloqueio de cartão (PRD-007) ---------------------------------------------------------------


def test_bloqueaveis_sao_os_cartoes_ativos_sem_bloqueio_do_canal():
    cartoes = [
        Cartao("CRT-1", "Tarjeta Crédito", "9241", "Active"),
        Cartao("CRT-2", "Tarjeta Débito", "5678", "Active", bloqueio="BL-00000001"),
        Cartao("CRT-3", "Tarjeta Crédito", "0000", "Closed"),
        Cartao("CRT-4", "Tarjeta Débito", "1111", "Blocked"),
        Cartao("CRT-5", "Tarjeta Crédito", None, "Suspended"),
        Cartao("CRT-6", "Tarjeta Débito", None, "Active"),
    ]
    assert [c.product_id for c in bloqueaveis(cartoes)] == ["CRT-1", "CRT-6"]


@pytest.mark.parametrize(
    ("quantos", "dispositivo", "esperado"),
    [
        (0, "cadastrado", Decisao("POL-BLQ-03", "responder", "nenhum cartão ativo para bloquear")),
        (0, "novo", Decisao("POL-BLQ-03", "responder", "nenhum cartão ativo para bloquear")),
        (2, "cadastrado", Decisao("POL-BLQ-06", "esclarecer")),
        (3, "novo", Decisao("POL-BLQ-06", "esclarecer")),
        (1, "cadastrado", Decisao("POL-BLQ-02", "bloquear_cartao", "completo")),
        (1, "novo", Decisao("POL-BLQ-01", "humano", "preventivo")),
    ],
)
def test_bloqueio_pelo_numero_de_cartoes_e_pelo_dispositivo(quantos, dispositivo, esperado):
    """Nenhum cartão bloqueável só informa; vários, pergunta qual (não escolhe sozinho); um só,
    bloqueia na hora: completo com dispositivo cadastrado, preventivo e com atendente com novo."""
    assert decidir_bloqueio(quantos, dispositivo) == esperado
