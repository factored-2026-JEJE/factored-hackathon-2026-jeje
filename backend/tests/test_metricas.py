"""Métricas (G11): recomputadas dos eventos e conferidas contra um cálculo independente
(biblioteca padrão do Python), inclusive a partir de conversas reais pela API."""

import json
import os
import statistics
import subprocess
import sys

import pytest
from conftest import abrir_conversa, autenticar, cliente, conexao, dizer
from sqlalchemy import text

from jeje import metricas

# (conversa, ação, regra, latência) de turnos conhecidos + dois erros.
TURNOS = [
    ("c1", "esclarecer", "POL-CON-02", 30), ("c1", "propor_pre_caso", "POL-DISP-01", 10),
    ("c1", "registrar_pre_caso", "POL-DISP-01", 100), ("c2", "humano", "POL-HUM-01", 20),
    ("c3", "responder", "POL-CON-03", 50), ("c3", "humano", "POL-HUM-03", 40),
    ("c4", "propor_pre_caso", "POL-DISP-01", 60), ("c4", "registrar_pre_caso", "POL-DISP-01", 90),
    ("c4", "recusar", "POL-ESC-01", 70), ("c4", "aguardar_humano", "COM-HUMANO", 80),
]  # fmt: skip


@pytest.fixture
def com_eventos(banco_migrado):
    with conexao(banco_migrado) as con:
        for conversa, acao, regra, latencia in TURNOS:
            con.execute(
                text(
                    "INSERT INTO app.eventos (tipo, conversa_id, acao, regra, latencia_ms)"
                    " VALUES ('turno', :c, :a, :r, :l)"
                ),
                {"c": conversa, "a": acao, "r": regra, "l": latencia},
            )
        for conversa in ("c2", "c5"):
            con.execute(
                text(
                    "INSERT INTO app.eventos (tipo, conversa_id, erro, latencia_ms)"
                    " VALUES ('erro', :c, 'InternalError', 5)"
                ),
                {"c": conversa},
            )
    return banco_migrado


def contagem(indice: int) -> dict[str, int]:
    valores = [t[indice] for t in TURNOS]
    return {valor: valores.count(valor) for valor in sorted(set(valores))}


def esperado() -> dict:
    """Mesmas métricas, calculadas aqui sem SQL a partir da tabela TURNOS."""
    latencias = [t[3] for t in TURNOS]
    quantis = statistics.quantiles(latencias, n=100, method="inclusive")
    conversas = {t[0] for t in TURNOS}
    encaminhadas = {t[0] for t in TURNOS if t[1] == "humano"}
    return {
        "turnos": len(TURNOS),
        "erros": 2,
        "taxa_de_erro": 2 / (len(TURNOS) + 2),
        "conversas": len(conversas),
        "conversas_encaminhadas": len(encaminhadas),
        "taxa_de_encaminhamento": len(encaminhadas) / len(conversas),
        "pre_casos_registrados": sum(1 for t in TURNOS if t[1] == "registrar_pre_caso"),
        "latencia_ms": {"p50": quantis[49], "p95": quantis[94], "max": max(latencias)},
        "acoes": contagem(1),
        "regras": contagem(2),
    }


def test_metricas_recomputadas_dos_eventos(com_eventos):
    with conexao(com_eventos) as con:
        calculado = metricas.calcular(con)
    alvo = esperado()
    for campo in (
        "turnos",
        "erros",
        "conversas",
        "conversas_encaminhadas",
        "pre_casos_registrados",
    ):
        assert calculado[campo] == alvo[campo], campo
    for campo in ("taxa_de_erro", "taxa_de_encaminhamento"):
        assert calculado[campo] == pytest.approx(alvo[campo]), campo
    assert calculado["latencia_ms"] == pytest.approx(alvo["latencia_ms"])
    assert (calculado["acoes"], calculado["regras"]) == (alvo["acoes"], alvo["regras"])


def test_sem_eventos_nao_inventa_taxa_nem_latencia(banco_migrado):
    with conexao(banco_migrado) as con:
        calculado = metricas.calcular(con)
    assert calculado == {
        "turnos": 0, "erros": 0, "taxa_de_erro": None, "conversas": 0,
        "conversas_encaminhadas": 0, "taxa_de_encaminhamento": None, "pre_casos_registrados": 0,
        "latencia_ms": {"p50": None, "p95": None, "max": None}, "acoes": {}, "regras": {},
        "modelo": {"chamadas": 0, "fallbacks": 0, "tokens_entrada": 0, "tokens_saida": 0,
                   "chamadas_sem_contagem_de_tokens": 0},
    }  # fmt: skip


def test_linha_de_comando_da_os_mesmos_numeros_da_api(com_eventos):
    ambiente = {**os.environ, "DATABASE_URL": com_eventos.database_url}
    saida = subprocess.run(
        [sys.executable, "-m", "jeje.metricas"], env=ambiente, capture_output=True, text=True,
        check=True, timeout=60,
    ).stdout  # fmt: skip
    with cliente(com_eventos) as http:
        da_api = http.get("/metricas").json()
    assert json.loads(saida) == da_api
    assert da_api["turnos"] == len(TURNOS)


def test_metricas_de_conversas_reais_pela_api(cenario_conversa):
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        normal = abrir_conversa(http, auth, "es")
        dizer(http, auth, normal, "No reconozco el cobro de 45,90 en Streaming Plus")
        dizer(http, auth, normal, "sí")
        humano = abrir_conversa(http, auth, "pt")
        dizer(http, auth, humano, "roubaram meu cartão")
        dizer(http, auth, humano, "e agora?")
        ambiguo = abrir_conversa(http, auth, "es")
        dizer(http, auth, ambiguo, "No reconozco un cobro de 45,90")
        calculado = http.get("/metricas").json()
    assert (calculado["turnos"], calculado["erros"], calculado["conversas"]) == (5, 0, 3)
    assert calculado["conversas_encaminhadas"] == 1
    assert calculado["taxa_de_encaminhamento"] == pytest.approx(1 / 3)
    assert calculado["pre_casos_registrados"] == 1
    assert calculado["acoes"] == {
        "aguardar_humano": 1, "esclarecer": 1, "humano": 1, "propor_pre_caso": 1,
        "registrar_pre_caso": 1,
    }  # fmt: skip
    assert 0 < calculado["latencia_ms"]["p50"] <= calculado["latencia_ms"]["p95"]


def test_uso_do_modelo_conta_toda_chamada_e_nao_estima_tokens(banco_migrado):
    # (interpretação, latência do modelo, tokens de entrada, tokens de saída)
    turnos = [
        ("ollama:m", 900, 100, 20), ("ollama:m", 700, 50, 10),
        ("regras (fallback: URLError)", 3, None, None), ("regras", None, None, None),
        ("regras", None, None, None),
    ]  # fmt: skip
    with conexao(banco_migrado) as con:
        for interpretacao, ms, entrada, saida in turnos:
            con.execute(
                text(
                    "INSERT INTO app.eventos (tipo, conversa_id, acao, regra, latencia_ms,"
                    " interpretacao, modelo_latencia_ms, modelo_tokens_entrada,"
                    " modelo_tokens_saida)"
                    " VALUES ('turno', 'c1', 'responder', 'POL-CON-01', 10, :i, :ms, :e, :s)"
                ),
                {"i": interpretacao, "ms": ms, "e": entrada, "s": saida},
            )
        calculado = metricas.calcular(con)
    assert calculado["modelo"] == {
        "chamadas": 3, "fallbacks": 1, "tokens_entrada": 150, "tokens_saida": 30,
        "chamadas_sem_contagem_de_tokens": 1,
    }  # fmt: skip


def test_pre_casos_de_toda_origem_batem_com_os_gravados_e_toda_acao_deixa_evento(
    cenario_conversa,
):
    """Pré-caso pela conversa e pelo painel de contestação (rota direta): as métricas contam os
    dois, o total bate com os pré-casos gravados, e cada ação direta deixa seu evento (a repetição
    idempotente da confirmação não cria nada, então não conta)."""
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, "No reconozco el cobro de 45,90 en Streaming Plus")
        dizer(http, auth, conversa, "sí")
        proposta = http.post("/minhas/transacoes/TRX-A6/contestacao/proposta", headers=auth)
        confirmacao = f"/minhas/propostas/{proposta.json()['proposta']['id']}/confirmacao"
        confirmado = http.post(confirmacao, headers=auth)
        repetido = http.post(confirmacao, headers=auth)
        numeros = http.get("/metricas").json()
    with conexao(cenario_conversa) as con:
        gravados = con.execute(text("SELECT count(*) FROM app.pre_casos")).scalar_one()
        consulta = "SELECT acao, efeito FROM app.eventos WHERE tipo = 'acao' ORDER BY id"
        acoes = [tuple(linha) for linha in con.execute(text(consulta))]
    assert (proposta.status_code, confirmado.status_code, repetido.status_code) == (201, 201, 200)
    assert numeros["pre_casos_registrados"] == gravados == 2
    assert acoes == [
        ("propor_pre_caso", proposta.json()["proposta"]["id"]),
        ("registrar_pre_caso", confirmado.json()["protocolo"]),
    ]
