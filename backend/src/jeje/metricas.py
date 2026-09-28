"""Métricas recomputadas dos eventos (G11): todo número sai de `app.eventos`, nenhum é fixo.

`python -m jeje.metricas` imprime o mesmo JSON de `GET /metricas` (make metricas).
"""

import json

from sqlalchemy import Connection, text

from jeje.config import Settings
from jeje.db import create_db_engine


def _taxa(parte: int, todo: int) -> float | None:
    return None if todo == 0 else parte / todo


def calcular(conexao: Connection) -> dict:
    geral = conexao.execute(
        text(
            "SELECT count(*) FILTER (WHERE tipo = 'turno') AS turnos,"
            " count(*) FILTER (WHERE tipo = 'erro') AS erros,"
            " count(DISTINCT conversa_id) FILTER (WHERE tipo = 'turno') AS conversas,"
            " count(DISTINCT conversa_id) FILTER (WHERE tipo = 'turno' AND acao = 'humano')"
            "   AS encaminhadas,"
            " count(*) FILTER (WHERE tipo = 'turno' AND acao = 'registrar_pre_caso') AS pre_casos,"
            " percentile_cont(0.5) WITHIN GROUP (ORDER BY latencia_ms)"
            "   FILTER (WHERE tipo = 'turno') AS p50,"
            " percentile_cont(0.95) WITHIN GROUP (ORDER BY latencia_ms)"
            "   FILTER (WHERE tipo = 'turno') AS p95,"
            " max(latencia_ms) FILTER (WHERE tipo = 'turno') AS maximo,"
            " count(*) FILTER (WHERE modelo_latencia_ms IS NOT NULL) AS chamadas,"
            " count(*) FILTER (WHERE interpretacao LIKE 'regras (fallback:%') AS fallbacks,"
            " count(*) FILTER (WHERE modelo_latencia_ms IS NOT NULL AND"
            "   (modelo_tokens_entrada IS NULL OR modelo_tokens_saida IS NULL)) AS sem_contagem,"
            " coalesce(sum(modelo_tokens_entrada), 0) AS tokens_entrada,"
            " coalesce(sum(modelo_tokens_saida), 0) AS tokens_saida"
            " FROM app.eventos"
        )
    ).one()
    por = {}
    for coluna in ("acao", "regra"):
        linhas = conexao.execute(
            text(
                f"SELECT {coluna}, count(*) FROM app.eventos WHERE tipo = 'turno'"
                f" GROUP BY {coluna} ORDER BY {coluna}"
            )
        )
        por[coluna] = {chave: total for chave, total in linhas}
    return {
        "turnos": geral.turnos,
        "erros": geral.erros,
        "taxa_de_erro": _taxa(geral.erros, geral.turnos + geral.erros),
        "conversas": geral.conversas,
        "conversas_encaminhadas": geral.encaminhadas,
        "taxa_de_encaminhamento": _taxa(geral.encaminhadas, geral.conversas),
        "pre_casos_registrados": geral.pre_casos,
        "latencia_ms": {
            "p50": geral.p50,
            "p95": geral.p95,
            "max": None if geral.maximo is None else float(geral.maximo),
        },
        "acoes": por["acao"],
        "regras": por["regra"],
        # Modelo local (G14): toda chamada despachada conta, inclusive as que caíram no fallback;
        # tokens não informados pelo servidor não são estimados, só contados à parte.
        "modelo": {
            "chamadas": geral.chamadas,
            "fallbacks": geral.fallbacks,
            "tokens_entrada": geral.tokens_entrada,
            "tokens_saida": geral.tokens_saida,
            "chamadas_sem_contagem_de_tokens": geral.sem_contagem,
        },
    }


def main() -> None:
    engine = create_db_engine(Settings())
    try:
        with engine.connect() as conexao:
            print(json.dumps(calcular(conexao), ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
