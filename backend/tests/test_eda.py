"""Indicadores da EDA num cenário pequeno, com proporções e denominadores calculados à mão."""

import pytest
from conftest import cliente as cliente_http
from conftest import conexao, curar_tudo, inserir_raw, raw_transacao
from sqlalchemy import text

from jeje import eda


@pytest.fixture
def cenario(base):
    with conexao(base) as con:
        for duracao, resolvido in (("100", "True"), ("200", "True"), ("300", "False")):
            inserir_raw(
                con,
                "call_center_interactions",
                interaction_id=f"INT-T{duracao}",
                reason_category="Transaccional",
                duration_seconds=duracao,
                was_resolved=resolvido,
            )
        inserir_raw(
            con,
            "call_center_interactions",
            interaction_id="INT-Q1",
            reason_category="Queja",
            duration_seconds="400",
            was_resolved="False",
        )
        inserir_raw(
            con,
            "call_center_interactions",
            interaction_id="INT-Q2",
            reason_category="Queja",
            duration_seconds="x",
            was_resolved="False",
        )
        raw_transacao(con, "TRX-1", "CLI-A", "PRD-A")
        raw_transacao(con, "TRX-2", "CLI-A", "PRD-A")
        raw_transacao(
            con, "TRX-3", "CLI-A", "PRD-A", transaction_status="Declined", response_code="51"
        )
        raw_transacao(con, "TRX-4", "CLI-A", "PRD-A", transaction_status="Declined")
        for cid, categoria, sub in (
            ("C1", "Transactions", "Cargo no reconocido"),
            ("C2", "Transactions", None),
            ("C3", "Fees", None),
        ):
            inserir_raw(
                con,
                "complaints",
                complaint_id=cid,
                creation_date="2025-03-10 10:00:00",
                customer_id="CLI-A",
                case_type="Claim",
                status="Open",
                category=categoria,
                subcategory=sub,
            )
        for tid, idioma in (("T1", "es"), ("T2", "es"), ("T3", "pt")):
            inserir_raw(con, "call_transcripts", transcript_id=tid, detected_language=idioma)
    curar_tudo(base)
    return base


def resultado(settings, id_indicador: str) -> eda.Resultado:
    indicador = next(i for i in eda.INDICADORES if i.id == id_indicador)
    with conexao(settings) as con:
        return eda.calcular(con, indicador)


def resumo(r: eda.Resultado) -> list[tuple]:
    return [
        (linha.grupo, linha.contagem, linha.base, round(linha.proporcao, 4)) for linha in r.linhas
    ]


def test_motivos_de_contato_contagem_e_tempo_ignorando_duracao_invalida(cenario):
    r = resultado(cenario, "motivos-de-contato")
    assert resumo(r) == [("Transaccional", 3, 5, 0.6), ("Queja", 2, 5, 0.4)]
    assert [(linha.soma, round(linha.proporcao_soma, 4)) for linha in r.linhas] == [
        (600.0, 0.6),
        (400.0, 0.4),
    ]


def test_resolucao_e_taxa_dentro_de_cada_motivo(cenario):
    r = resultado(cenario, "resolucao-por-motivo")
    assert resumo(r) == [("Queja", 0, 2, 0.0), ("Transaccional", 2, 3, 0.6667)]


def test_status_e_codigos_das_recusas(cenario):
    assert resumo(resultado(cenario, "status-das-transacoes")) == [
        ("Approved", 2, 4, 0.5), ("Declined", 2, 4, 0.5),
    ]  # fmt: skip
    assert resumo(resultado(cenario, "codigos-nas-recusas")) == [
        ("(sem código)", 1, 2, 0.5), ("51", 1, 2, 0.5),
    ]  # fmt: skip


def test_reclamacoes_por_categoria_e_subcategorias_de_transacao(cenario):
    assert resumo(resultado(cenario, "reclamacoes-por-categoria")) == [
        ("Transactions", 2, 3, 0.6667), ("Fees", 1, 3, 0.3333),
    ]  # fmt: skip
    assert resumo(resultado(cenario, "reclamacoes-de-transacao")) == [
        ("(vazio)", 1, 2, 0.5), ("Cargo no reconocido", 1, 2, 0.5),
    ]  # fmt: skip


def test_idiomas_das_transcricoes(cenario):
    assert resumo(resultado(cenario, "idiomas-nas-transcricoes")) == [
        ("es", 2, 3, 0.6667), ("pt", 1, 3, 0.3333),
    ]  # fmt: skip


def test_rota_publica_a_consulta_que_de_fato_produziu_os_numeros(cenario):
    with cliente_http(cenario) as http:
        indicadores = http.get("/dados/eda").json()
    assert [i["id"] for i in indicadores] == [i.id for i in eda.INDICADORES]
    with conexao(cenario) as con:
        for publicado in indicadores:
            refeito = con.execute(text(publicado["consulta"])).mappings().all()
            assert [(r["grupo"], r["contagem"]) for r in refeito] == [
                (linha["grupo"], linha["contagem"]) for linha in publicado["linhas"]
            ]
