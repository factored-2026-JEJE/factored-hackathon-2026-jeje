"""A tabela do teste final no topo do README (2.14 do fechamento, DEV-022a), escrita pelo time do
produto, não pela validação.

Lê o mesmo arquivo que o site mostra, `frontend/public/resultados/teste-final.json`, na forma que o
site aceita (frontend/src/site/resultados.ts): `{commit, evidencia, n, linhas: {baseline, execucao1,
execucao2}}`, cada linha com as 9 células do design. Escreve a tabela em inglês, com os rótulos do
site, entre os marcadores do README. Nenhum número é digitado à mão; com o arquivo fora da forma, nada
muda e a saída é 1. Rodar da raiz do repositório:

  python -m avaliacao.readme [--resultados <json>] [--readme <README.md>] [--conferir]

Com --conferir, só confere se o README já tem a tabela do arquivo (saída 1 se não tiver).
"""

import argparse
import json
import math
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RESULTADOS = RAIZ / "frontend" / "public" / "resultados" / "teste-final.json"
README = RAIZ / "README.md"
INICIO = "<!-- tabela-do-teste-final:inicio -->"
FIM = "<!-- tabela-do-teste-final:fim -->"
# Os rótulos do site em inglês (frontend/src/site/conteudo.ts, results.cols e results.rows).
COLUNAS = (
    "Safe resolution",
    "Coverage",
    "Containment",
    "Missed handoff",
    "Needless handoff",
    "Unsafe cases",
    "Grounding",
    "p50 / p95",
    "Cost",
)
LINHAS = (
    ("baseline", "Baseline · rules only"),
    ("execucao1", "System · run 1"),
    ("execucao2", "System · run 2"),
)


def _numero(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _celula_valida(c: object) -> bool:
    """As formas de célula que o site aceita (validarResultados)."""
    if c is None:
        return True
    if not isinstance(c, dict):
        return False
    if "fracao" in c:
        return _numero(c["fracao"]) and 0 <= c["fracao"] <= 1
    if "contagem" in c:
        return _numero(c["contagem"]) and _numero(c.get("de")) and c["de"] > 0
    if "ms" in c:
        ms = c["ms"]
        return isinstance(ms, list) and len(ms) == 2 and all(_numero(x) for x in ms)
    if "numero" in c:
        return _numero(c["numero"]) and isinstance(c.get("unidade", ""), str)
    return False


def validar(dados: object) -> dict | None:
    """O arquivo, se tiver a forma do site; senão, None (a tabela não sai pela metade)."""
    if not isinstance(dados, dict):
        return None
    if not isinstance(dados.get("commit"), str) or not isinstance(dados.get("evidencia"), str):
        return None
    if not _numero(dados.get("n")):
        return None
    linhas = dados.get("linhas")
    if not isinstance(linhas, dict):
        return None
    for chave, _ in LINHAS:
        linha = linhas.get(chave)
        if not isinstance(linha, list) or len(linha) != len(COLUNAS):
            return None
        if not all(_celula_valida(c) for c in linha):
            return None
    return dados


def _fixo(x: float, casas: int) -> str:
    """Como o toLocaleString do site em inglês: a metade arredonda para longe do zero (91,25 → 91.3),
    e não para o par, como o format do Python."""
    exato = Decimal(x).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)
    return f"{exato:,.{casas}f}"


def celula(c: dict | None) -> str:
    """A célula como o site a mostra em inglês (formatarCelula)."""
    if c is None:
        return "—"
    if "fracao" in c:
        return _fixo(c["fracao"] * 100, 1) + "%"
    if "contagem" in c:
        return f"{c['contagem']:g} / {c['de']:g}"
    if "ms" in c:
        return f"{_fixo(c['ms'][0], 0)} / {_fixo(c['ms'][1], 0)} ms"
    unidade = f" {c['unidade']}" if c.get("unidade") else ""
    return _fixo(c["numero"], 2) + unidade


def tabela(dados: dict) -> str:
    """O bloco entre os marcadores: a tabela e a linha de onde ela vem."""
    cabecalho = "| | " + " | ".join(COLUNAS) + " |"
    separador = "| --- |" + " ---: |" * len(COLUNAS)
    linhas = [
        f"| {rotulo} | " + " | ".join(celula(c) for c in dados["linhas"][chave]) + " |"
        for chave, rotulo in LINHAS
    ]
    origem = (
        f"_The final test: {dados['n']:g} held-out scenarios, run once on the frozen commit "
        f"`{dados['commit'][:12]}` ({dados['evidencia']}); the same numbers on the site._"
    )
    return "\n".join([cabecalho, separador, *linhas, "", origem])


def com_a_tabela(texto: str, bloco: str) -> str | None:
    """O README com o bloco entre os marcadores; None se os marcadores não estiverem lá, uma vez cada."""
    if texto.count(INICIO) != 1 or texto.count(FIM) != 1:
        return None
    antes, resto = texto.split(INICIO)
    _, depois = resto.split(FIM)
    return f"{antes}{INICIO}\n{bloco}\n{FIM}{depois}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--resultados", type=Path, default=RESULTADOS)
    parser.add_argument("--readme", type=Path, default=README)
    parser.add_argument("--conferir", action="store_true")
    argumentos = parser.parse_args(argv)
    try:
        dados = validar(json.loads(argumentos.resultados.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        dados = None
    if dados is None:
        print(f"[readme] {argumentos.resultados} fora da forma do site: nada muda")
        return 1
    texto = argumentos.readme.read_text(encoding="utf-8")
    novo = com_a_tabela(texto, tabela(dados))
    if novo is None:
        print(f"[readme] os marcadores da tabela não estão em {argumentos.readme}, uma vez cada")
        return 1
    if argumentos.conferir:
        return 0 if novo == texto else 1
    argumentos.readme.write_text(novo, encoding="utf-8")
    print(f"[readme] tabela do commit {dados['commit'][:12]} escrita em {argumentos.readme}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
