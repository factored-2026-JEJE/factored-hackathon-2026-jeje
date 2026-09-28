"""Harness de mutantes: prova que cada teste detecta um defeito realista (ENG-004).

Para cada mutante do registro, copia o código para um diretório temporário (a árvore de trabalho
nunca é alterada), aplica trocas exatas de texto e roda os testes associados:

- mutante comum: os testes PRECISAM falhar (ou estourar o tempo) — senão o teste é fraco;
- mutante de controle (`"espera": "sobrevive"`): mudança sem efeito; a suíte PRECISA passar —
  prova que o harness não reporta "morto" por erro de ambiente.

Antes de tudo a suíte original precisa passar. Por fim, todo teste coletado precisa estar ligado a
pelo menos um mutante (cobertura de sensibilidade). Só usa a biblioteca padrão.

Uso: python executar.py <registro.json> [--so ID ...]
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

IGNORAR = shutil.ignore_patterns(
    ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules"
)


class ErroDeRegistro(Exception):
    """Registro inconsistente com o código (ex.: trecho a trocar não existe ou é ambíguo)."""


def rodar(comando: list[str], cwd: Path, timeout_s: int, env: dict) -> tuple[str, float, str]:
    """Executa e devolve ("passou" | "falhou" | "tempo", segundos, fim da saída).

    Mata o grupo de processos no timeout (conta como mutante morto: o teste não passou)."""
    inicio = time.monotonic()
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as saida:
        processo = subprocess.Popen(
            comando,
            cwd=cwd,
            env=env,
            stdout=saida,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            codigo = processo.wait(timeout=timeout_s)
            resultado = "passou" if codigo == 0 else "falhou"
        except subprocess.TimeoutExpired:
            os.killpg(processo.pid, signal.SIGKILL)
            processo.wait()
            resultado = "tempo"
        saida.seek(0)
        fim = "".join(saida.readlines()[-30:])
    return resultado, time.monotonic() - inicio, fim


def aplicar_trocas(raiz: Path, trocas: list[dict], id_mutante: str) -> None:
    for troca in trocas:
        arquivo = raiz / troca["arquivo"]
        if not arquivo.is_file():
            raise ErroDeRegistro(f"{id_mutante}: arquivo inexistente {troca['arquivo']}")
        conteudo = arquivo.read_text(encoding="utf-8")
        ocorrencias = conteudo.count(troca["de"])
        if ocorrencias != 1:
            raise ErroDeRegistro(
                f"{id_mutante}: trecho encontrado {ocorrencias}x em {troca['arquivo']} (exige 1)"
            )
        arquivo.write_text(conteudo.replace(troca["de"], troca["para"]), encoding="utf-8")


def ambiente_para(raiz: Path, registro: dict) -> dict:
    env = dict(os.environ)
    for chave, valor in registro.get("ambiente", {}).items():
        env[chave] = valor.replace("{raiz}", str(raiz))
    return env


def argumentos_de_teste(registro: dict, testes: list[str]) -> list[str]:
    """Traduz IDs do registro para a linha de comando do executor."""
    if registro["executor"] == "pytest":
        return list(testes)
    if registro["executor"] == "vitest":
        # ID "arquivo > nome do teste" (filtro de arquivo + nome exato em -t) ou caminho inteiro.
        arquivos, nomes = set(), []
        for teste in testes:
            arquivo, _, nome = teste.partition(" > ")
            arquivos.add(arquivo)
            if nome:
                nomes.append(re.escape(nome))
        filtro_nome = ["-t", "^(?:" + "|".join(nomes) + ")$"] if nomes else []
        return [*sorted(arquivos), *filtro_nome]
    raise ErroDeRegistro(f"executor desconhecido: {registro['executor']}")


def coletar_ids(registro: dict, base: Path, env: dict) -> set[str]:
    saida = subprocess.run(
        registro["comando_coleta"], cwd=base, env=env, capture_output=True, text=True, check=True
    ).stdout
    if registro["executor"] == "pytest":
        return {re.sub(r"\[.*\]$", "", linha) for linha in saida.splitlines() if "::" in linha}
    if registro["executor"] == "vitest":
        return {f"{os.path.relpath(t['file'], base)} > {t['name']}" for t in json.loads(saida)}
    raise ErroDeRegistro(f"executor desconhecido: {registro['executor']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("registro")
    parser.add_argument("--so", nargs="*", help="executa apenas estes IDs (sem meta-check)")
    args = parser.parse_args()

    registro = json.loads(Path(args.registro).read_text(encoding="utf-8"))
    base = Path(registro["diretorio"])
    timeout_padrao = registro["timeout_s"]
    mutantes = registro["mutantes"]
    if args.so:
        mutantes = [m for m in mutantes if m["id"] in set(args.so)]
    ids = [m["id"] for m in registro["mutantes"]]
    if len(ids) != len(set(ids)):
        print("ERRO: IDs de mutante repetidos", file=sys.stderr)
        return 1

    print(f"[base] suíte original em {base}")
    resultado, _, fim = rodar(
        registro["comando_teste"], base, timeout_padrao * 3, ambiente_para(base, registro)
    )
    if resultado != "passou":
        print(fim, file=sys.stderr)
        print("ERRO: suíte original vermelha; mutantes não significam nada.", file=sys.stderr)
        return 1

    problemas: list[str] = []
    linhas = []
    for mutante in mutantes:
        espera = mutante.get("espera", "morre")
        with tempfile.TemporaryDirectory(prefix=f"mut-{mutante['id']}-") as tmp:
            raiz = Path(tmp) / "codigo"
            shutil.copytree(base, raiz, ignore=IGNORAR, symlinks=True)
            if (base / "node_modules").exists():
                (raiz / "node_modules").symlink_to(base / "node_modules")
            try:
                aplicar_trocas(raiz, mutante["trocas"], mutante["id"])
                selecao = argumentos_de_teste(registro, mutante["testes"])
                comando = registro["comando_teste"] + selecao
            except ErroDeRegistro as erro:
                problemas.append(str(erro))
                linhas.append((mutante["id"], mutante.get("requisito", "-"), "ERRO", 0.0))
                continue
            timeout = mutante.get("timeout_s", timeout_padrao)
            resultado, segundos, fim = rodar(comando, raiz, timeout, ambiente_para(raiz, registro))
        morto = resultado in ("falhou", "tempo")
        if espera == "sobrevive":
            ok = not morto
            situacao = "controle ok" if ok else "CONTROLE MORREU (harness/ambiente suspeito)"
            if not ok:
                print(fim, file=sys.stderr)
        else:
            ok = morto
            situacao = f"morto ({resultado})" if ok else "SOBREVIVEU (teste fraco)"
        if not ok:
            problemas.append(f"{mutante['id']}: {situacao}")
        linhas.append((mutante["id"], mutante.get("requisito", "-"), situacao, segundos))

    largura = max((len(linha[0]) for linha in linhas), default=10)
    for id_mutante, requisito, situacao, segundos in linhas:
        print(f"{id_mutante:<{largura}}  {requisito:<10} {situacao:<45} {segundos:6.1f}s")

    if not args.so:
        cobertos = {
            teste
            for m in registro["mutantes"]
            if m.get("espera", "morre") == "morre"
            for teste in m["testes"]
        }
        coletados = coletar_ids(registro, base, ambiente_para(base, registro))
        sem_mutante = sorted(coletados - cobertos)
        inexistentes = sorted(cobertos - coletados)
        for teste in sem_mutante:
            problemas.append(f"teste sem mutante que o derrube: {teste}")
        for teste in inexistentes:
            problemas.append(f"registro cita teste inexistente: {teste}")
        com_mutante = len(coletados) - len(sem_mutante)
        print(f"[cobertura] {len(coletados)} testes coletados, {com_mutante} com mutante")

    if problemas:
        print("\nFALHOU:", file=sys.stderr)
        for problema in problemas:
            print(f" - {problema}", file=sys.stderr)
        return 1
    print(f"\nOK: {len(linhas)} mutantes conforme o esperado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
