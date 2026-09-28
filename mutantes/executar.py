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
import contextlib
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

# Nunca copiados para a área do mutante: caches, dependências, histórico, segredos e dados brutos.
NOMES_IGNORADOS = {
    ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", ".git", ".env",
    "test-results", "playwright-report",
}  # fmt: skip


def ignorar(diretorio: str, nomes: list[str]) -> set[str]:
    ignorados = {nome for nome in nomes if nome in NOMES_IGNORADOS}
    if Path(diretorio).name == "data" and "raw" in nomes:
        ignorados.add("raw")
    return ignorados


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


def ambiente_para(raiz: Path, registro: dict, extra: dict | None = None) -> dict:
    env = dict(os.environ)
    for chave, valor in registro.get("ambiente", {}).items():
        env[chave] = valor.replace("{raiz}", str(raiz))
    env.update(extra or {})
    return env


def prefixo_de_projeto() -> str:
    """Prefixo dos projetos compose das stacks (ACH-023): execuções paralelas usam prefixos
    diferentes, definidos no compose (`MUTANTES_PREFIXO`)."""
    return os.environ["MUTANTES_PREFIXO"]


class StackIndisponivel(Exception):
    """A stack do mutante não subiu: o mutante é inválido, não conta como detectado."""


@contextlib.contextmanager
def stack(registro: dict, raiz: Path, rotulo: str):
    """Sobe uma stack compose isolada (projeto, imagens e rede próprios) e a destrói ao final."""
    projeto = f"{prefixo_de_projeto()}-" + re.sub(r"[^a-z0-9]+", "-", rotulo.lower()).strip("-")
    env = ambiente_para(raiz, registro, {"MUTANTE_TAG": projeto})
    compose = ["docker", "compose", "-p", projeto, *registro["compose_args"]]
    try:
        resultado, _, fim = rodar(
            [*compose, "up", "-d", "--build", "--wait", *registro["servicos_stack"]],
            raiz,
            registro["timeout_stack_s"],
            env,
        )
        if resultado != "passou":
            raise StackIndisponivel(f"{rotulo}: stack não subiu ({resultado})\n{fim}")
        yield compose, env
    finally:
        subprocess.run(
            [*compose, "--profile", "e2e", "down", "-v", "--remove-orphans"],
            cwd=raiz, env=env, capture_output=True, check=False,
        )  # fmt: skip
        remover_imagens_do_projeto(projeto)


def executar_testes(
    registro: dict, raiz: Path, testes: list[str] | None, timeout_s: int, rotulo: str
) -> tuple[str, float, str]:
    """Roda a suíte (testes=None) ou a seleção indicada no código em `raiz`."""
    selecao = argumentos_de_teste(registro, testes) if testes else []
    if registro["executor"] != "playwright-stack":
        comando = registro["comando_teste"] + selecao
        return rodar(comando, raiz, timeout_s, ambiente_para(raiz, registro))
    with stack(registro, raiz, rotulo) as (compose, env):
        comando = [*compose, "--profile", "e2e", *registro["comando_teste"], *selecao]
        return rodar(comando, raiz, timeout_s, env)


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
    if registro["executor"] == "playwright-stack":
        # ID "arquivo > título": arquivo como filtro e título em --grep (caminho completo).
        arquivos, titulos = set(), []
        for teste in testes:
            arquivo, _, titulo = teste.partition(" > ")
            arquivos.add(re.escape(arquivo))
            if titulo:
                titulos.append(re.escape(titulo))
        filtro_titulo = ["--grep", "|".join(titulos)] if titulos else []
        return [*sorted(arquivos), *filtro_titulo]
    raise ErroDeRegistro(f"executor desconhecido: {registro['executor']}")


def remover_imagens_do_projeto(projeto: str) -> None:
    imagens = subprocess.run(
        ["docker", "images", "-q", "--filter", f"reference=*:{projeto}"],
        capture_output=True, text=True, check=False,
    ).stdout.split()  # fmt: skip
    if imagens:
        subprocess.run(["docker", "rmi", "-f", *imagens], capture_output=True, check=False)


def coletar_ids(registro: dict, raiz: Path) -> set[str]:
    """IDs de todos os testes existentes, no mesmo formato usado no registro."""
    comando = registro["comando_coleta"]
    env = ambiente_para(raiz, registro)
    if registro["executor"] == "playwright-stack":
        projeto = f"{prefixo_de_projeto()}-coleta"
        env["MUTANTE_TAG"] = projeto
        comando = ["docker", "compose", "-p", projeto, *registro["compose_args"], *comando]
    try:
        saida = subprocess.run(
            comando, cwd=raiz, env=env, capture_output=True, text=True, check=True
        ).stdout
    finally:
        if registro["executor"] == "playwright-stack":
            subprocess.run(
                ["docker", "compose", "-p", projeto, *registro["compose_args"],
                 "--profile", "e2e", "down", "-v", "--remove-orphans"],
                cwd=raiz, env=env, capture_output=True, check=False,
            )  # fmt: skip
            remover_imagens_do_projeto(projeto)
    if registro["executor"] == "pytest":
        return {re.sub(r"\[.*\]$", "", linha) for linha in saida.splitlines() if "::" in linha}
    if registro["executor"] == "vitest":
        return {f"{os.path.relpath(t['file'], raiz)} > {t['name']}" for t in json.loads(saida)}
    if registro["executor"] == "playwright-stack":
        ids: set[str] = set()
        pendentes = list(json.loads(saida[saida.index("{") :])["suites"])
        while pendentes:
            suite = pendentes.pop()
            pendentes.extend(suite.get("suites", []))
            ids.update(f"{spec['file']} > {spec['title']}" for spec in suite.get("specs", []))
        return ids
    raise ErroDeRegistro(f"executor desconhecido: {registro['executor']}")


def copiar(base: Path, destino: Path) -> None:
    shutil.copytree(base, destino, ignore=ignorar, symlinks=True)
    if (base / "node_modules").exists():
        (destino / "node_modules").symlink_to(base / "node_modules")


def avaliar(mutante: dict, resultado: str) -> tuple[bool, str]:
    morto = resultado in ("falhou", "tempo")
    if mutante.get("espera", "morre") == "sobrevive":
        if morto:
            return False, "CONTROLE MORREU (harness/ambiente suspeito)"
        return True, "controle ok"
    if morto:
        return True, f"morto ({resultado})"
    return False, "SOBREVIVEU (teste fraco)"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("registro")
    parser.add_argument("--so", nargs="*", help="executa apenas estes IDs (sem meta-check)")
    args = parser.parse_args()

    registro = json.loads(Path(args.registro).read_text(encoding="utf-8"))
    base = Path(registro["diretorio"])
    timeout_padrao = registro["timeout_s"]
    # A suíte inteira cresce com o projeto; cada mutante roda só a seleção dele.
    timeout_base = registro["timeout_base_s"]
    ids = [m["id"] for m in registro["mutantes"]]
    if len(ids) != len(set(ids)):
        print("ERRO: IDs de mutante repetidos", file=sys.stderr)
        return 1
    mutantes = [m for m in registro["mutantes"] if not args.so or m["id"] in set(args.so)]

    problemas: list[str] = []
    with tempfile.TemporaryDirectory(prefix="mut-base-") as tmp:
        raiz_base = Path(tmp) / "codigo"
        copiar(base, raiz_base)
        print(f"[base] suíte original de {base}")
        try:
            resultado, _, fim = executar_testes(registro, raiz_base, None, timeout_base, "base")
        except StackIndisponivel as erro:
            print(erro, file=sys.stderr)
            return 1
        if resultado != "passou":
            print(fim, file=sys.stderr)
            print("ERRO: suíte original vermelha; mutantes não significam nada.", file=sys.stderr)
            return 1
        coletados = None if args.so else coletar_ids(registro, raiz_base)

    linhas = []
    for mutante in mutantes:
        with tempfile.TemporaryDirectory(prefix=f"mut-{mutante['id']}-") as tmp:
            raiz = Path(tmp) / "codigo"
            copiar(base, raiz)
            try:
                aplicar_trocas(raiz, mutante["trocas"], mutante["id"])
                # O controle roda a suíte como a base; os demais, só a seleção deles.
                controle = mutante.get("espera") == "sobrevive"
                timeout = mutante.get("timeout_s", timeout_base if controle else timeout_padrao)
                resultado, segundos, fim = executar_testes(
                    registro, raiz, mutante["testes"], timeout, mutante["id"]
                )
            except (ErroDeRegistro, StackIndisponivel) as erro:
                problemas.append(str(erro))
                linhas.append((mutante["id"], mutante.get("requisito", "-"), "ERRO", 0.0))
                continue
        ok, situacao = avaliar(mutante, resultado)
        if not ok:
            problemas.append(f"{mutante['id']}: {situacao}")
            if mutante.get("espera") == "sobrevive":
                print(fim, file=sys.stderr)
        linhas.append((mutante["id"], mutante.get("requisito", "-"), situacao, segundos))

    largura = max((len(linha[0]) for linha in linhas), default=10)
    for id_mutante, requisito, situacao, segundos in linhas:
        print(f"{id_mutante:<{largura}}  {requisito:<10} {situacao:<45} {segundos:6.1f}s")

    if coletados is not None:
        cobertos = {
            teste
            for m in registro["mutantes"]
            if m.get("espera", "morre") == "morre"
            for teste in m["testes"]
        }
        sem_mutante = sorted(coletados - cobertos)
        for teste in sem_mutante:
            problemas.append(f"teste sem mutante que o derrube: {teste}")
        for teste in sorted(cobertos - coletados):
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
