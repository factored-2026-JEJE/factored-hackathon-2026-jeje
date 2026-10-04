"""A tabela da avaliação (EXP-002, adendo de 03/10), escrita pela validação: por rodada, as colunas
do site e do README, com o IC de Wilson de 95%; o pass^k das rodadas do sistema; e a diferença
pareada contra a linha de base, por idioma, com IC por bootstrap que reamostra famílias (as
versões ES e PT de uma família são traduções, não casos independentes).

As colunas, por rodada:
- resolução segura: resolvidos com segurança sobre os julgados;
- cobertura: concluídos sem passar ao atendente sobre os julgados (o que o sistema automatiza);
- contenção: entre os que não precisam de atendente, os resolvidos sem passar a ele;
- encaminhamento perdido: entre os que precisam de atendente, os que não chegaram a ele;
- encaminhamento desnecessário: entre os que não precisam, os que foram a ele;
- inseguros: resultados inseguros sobre os julgados;
- fundamentação: cenários rastreáveis (cada fato citado bate com a linha de origem);
- p50 e p95: das latências de cada envio, em ms (posto mais próximo);
- custo: turnos lidos pelo LLM do produto, no total e por cenário (medido).
"""

import math
import random
import statistics
from collections import defaultdict

SEMENTE = 20261001
Z_95 = 1.959963984540054


def taxa(sucessos: int, total: int) -> dict:
    """x de n, a proporção e o IC de Wilson de 95%."""
    if not total:
        return {"x": sucessos, "n": total, "taxa": None, "ic95": None}
    p = sucessos / total
    meio = Z_95**2 / (2 * total)
    raio = Z_95 * math.sqrt(p * (1 - p) / total + Z_95**2 / (4 * total**2))
    denominador = 1 + Z_95**2 / total
    ic = [round(max(0.0, (p + meio - raio) / denominador), 4)]
    ic.append(round(min(1.0, (p + meio + raio) / denominador), 4))
    return {"x": sucessos, "n": total, "taxa": round(p, 4), "ic95": ic}


def percentil(valores: list[float], q: float) -> float | None:
    """Percentil pelo posto mais próximo, sem interpolar (o p95 é uma latência que ocorreu)."""
    if not valores:
        return None
    ordenados = sorted(valores)
    posto = math.ceil(len(ordenados) * q / 100)
    return ordenados[max(0, min(len(ordenados) - 1, posto - 1))]


def colunas(cenarios: dict[str, dict]) -> dict:
    """As colunas de uma rodada a partir dos cenários julgados ({id: veredito com o esperado})."""
    julgados = {k: c for k, c in cenarios.items() if c.get("resolvido") is not None}
    precisam = [c for c in julgados.values() if c["esperado_humano"] is True]
    nao_precisam = [c for c in julgados.values() if c["esperado_humano"] is False]
    ms = [m for c in julgados.values() for m in c.get("ms") or []]
    llm = [c["pelo_llm"] for c in julgados.values() if c.get("pelo_llm") is not None]
    rastreaveis = [c["rastreavel"] for c in julgados.values() if c.get("rastreavel") is not None]
    todos = list(julgados.values())
    return {
        "resolucao_segura": taxa(sum(bool(c["resolvido"]) for c in todos), len(todos)),
        "cobertura": taxa(sum(not c["encaminhou"] for c in todos), len(todos)),
        "contencao": taxa(
            sum(bool(c["resolvido"]) and not c["encaminhou"] for c in nao_precisam),
            len(nao_precisam),
        ),
        "encaminhamento_perdido": taxa(sum(not c["encaminhou"] for c in precisam), len(precisam)),
        "encaminhamento_desnecessario": taxa(
            sum(bool(c["encaminhou"]) for c in nao_precisam), len(nao_precisam)
        ),
        "inseguros": taxa(sum(c["seguro"] is False for c in todos), len(todos)),
        "fundamentacao": taxa(sum(bool(v) for v in rastreaveis), len(rastreaveis)),
        "acerto_na_primeira_resposta": taxa(
            sum(c.get("na_primeira") == 1 for c in todos),
            sum(c.get("na_primeira") is not None for c in todos),
        ),
        "latencia_p50_ms": percentil(ms, 50),
        "latencia_p95_ms": percentil(ms, 95),
        "envios": len(ms),
        "turnos_pelo_llm": sum(llm) if llm else None,
        "turnos_pelo_llm_por_cenario": round(sum(llm) / len(llm), 3) if llm else None,
    }


def pass_k(rodadas: list[dict[str, dict]]) -> dict:
    """Cenários resolvidos com segurança em todas as k rodadas do sistema."""
    if not rodadas:
        return taxa(0, 0)
    comuns = set.intersection(*(set(r) for r in rodadas))
    validos = [c for c in comuns if all(r[c].get("resolvido") is not None for r in rodadas)]
    return taxa(sum(all(r[c]["resolvido"] for r in rodadas) for c in validos), len(validos))


def media_das_rodadas(rodadas: list[dict[str, dict]], metrica: str) -> dict[str, dict]:
    """Por cenário, a média da métrica nas k rodadas do sistema (o pareamento usa as k rodadas)."""
    comuns = set.intersection(*(set(r) for r in rodadas)) if rodadas else set()
    saida = {}
    for cid in comuns:
        valores = [r[cid].get(metrica) for r in rodadas]
        if all(v is not None for v in valores):
            saida[cid] = {**rodadas[0][cid], metrica: statistics.fmean(float(v) for v in valores)}
    return saida


def diferenca_pareada(
    sistema: dict[str, dict],
    baseline: dict[str, dict],
    metrica: str = "resolvido",
    idioma: str | None = None,
    reamostras: int = 10000,
) -> dict:
    """A métrica do sistema menos a da linha de base, por cenário, com IC de 95% por bootstrap de
    famílias; com `idioma`, só os cenários desse idioma."""
    familias = defaultdict(list)
    for cid, c in sistema.items():
        b = baseline.get(cid)
        if b is None or c.get(metrica) is None or b.get(metrica) is None:
            continue
        if idioma is not None and c["idioma"] != idioma:
            continue
        familias[c["familia"]].append(float(c[metrica]) - float(b[metrica]))
    chaves = sorted(familias)
    if not chaves:
        return {"n": 0}
    media = statistics.fmean(d for k in chaves for d in familias[k])
    gerador, medias = random.Random(SEMENTE), []
    for _ in range(reamostras):
        amostra = [d for k in (gerador.choice(chaves) for _ in chaves) for d in familias[k]]
        medias.append(statistics.fmean(amostra))
    medias.sort()
    return {
        "n": sum(len(v) for v in familias.values()),
        "familias": len(chaves),
        "diferenca": round(media, 4),
        "ic95": [
            round(medias[int(0.025 * reamostras)], 4),
            round(medias[int(0.975 * reamostras)], 4),
        ],
    }


def montar(rodadas: list[dict]) -> dict:
    """A tabela a partir das rodadas ({variante, rodada, cenarios}); a linha de base é `regras`."""
    linhas = [
        {"variante": r["variante"], "rodada": r["rodada"], "colunas": colunas(r["cenarios"])}
        for r in sorted(
            rodadas, key=lambda r: (r["variante"] != "regras", r["variante"], r["rodada"])
        )
    ]
    baseline = next((r["cenarios"] for r in rodadas if r["variante"] == "regras"), None)
    sistemas = defaultdict(list)
    for r in rodadas:
        if r["variante"] != "regras":
            sistemas[r["variante"]].append(r["cenarios"])
    comparacoes = {}
    for variante, lista in sistemas.items():
        comparacao = {"pass_k": pass_k(lista), "k": len(lista)}
        if baseline is not None:
            for metrica in ("resolvido", "na_primeira"):
                sistema = media_das_rodadas(lista, metrica)
                comparacao[metrica] = {
                    "todos": diferenca_pareada(sistema, baseline, metrica),
                    **{i: diferenca_pareada(sistema, baseline, metrica, i) for i in ("es", "pt")},
                }
        comparacoes[variante] = comparacao
    return {"linhas": linhas, "contra_a_linha_de_base": comparacoes}


def _celula(valor: dict) -> str:
    if valor["taxa"] is None:
        return "—"
    return f"{valor['x']}/{valor['n']} ({100 * valor['taxa']:.1f}%)"


def markdown(tabela: dict) -> str:
    cabecalho = (
        "| Variante | Resolução segura | Cobertura | Contenção | Encaminhamento perdido "
        "| Encaminhamento desnecessário | Inseguros | Fundamentação | p50 / p95 (ms) "
        "| Turnos no LLM |"
    )
    linhas = [cabecalho, "| --- |" + " ---: |" * 9]
    for linha in tabela["linhas"]:
        c = linha["colunas"]
        nomes = (
            "resolucao_segura",
            "cobertura",
            "contencao",
            "encaminhamento_perdido",
            "encaminhamento_desnecessario",
            "inseguros",
            "fundamentacao",
        )
        celulas = [_celula(c[nome]) for nome in nomes]
        latencia = "—"
        if c["latencia_p50_ms"] is not None:
            latencia = f"{c['latencia_p50_ms']:.0f} / {c['latencia_p95_ms']:.0f}"
        llm = "—" if c["turnos_pelo_llm"] is None else str(c["turnos_pelo_llm"])
        rotulo = f"{linha['variante']} (rodada {linha['rodada']})"
        linhas.append(f"| {rotulo} | " + " | ".join([*celulas, latencia, llm]) + " |")
    return "\n".join(linhas) + "\n"
