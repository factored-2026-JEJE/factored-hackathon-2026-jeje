"""Avaliação verificável (VAL-019, tarefa 2.11): os cenários de desenvolvimento e de validação
contra a API de uma stack com a base de avaliação carregada, julgados pelo estado final no banco,
e a tabela que o site e o README mostram.

O conjunto final do teste (VAL-019) não está aqui: ele roda uma vez, na versão congelada, e só
entra no repositório depois. Nunca roda contra a publicação: o alvo precisa ser loopback ou um
serviço do compose.

Uso:
  python -m avaliacao.avaliar base --destino <pasta>
  python -m avaliacao.avaliar rodar --url http://web:8080/api --base <pasta> --variante regras
      [--rodada 1] [--banco-url <URL do banco> | --compose "<docker compose ...>"] [--saida ...]
  python -m avaliacao.avaliar tabela resultados/avaliacao-<commit>-*.json [--saida ...]
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from avaliacao import avaliador, base, fixture, tabela
from avaliacao.api import alvo_local

RAIZ = Path(__file__).resolve().parent.parent
CENARIOS = Path(__file__).with_name("cenarios.json")


def limite_da_mensagem(produto: Path) -> int | None:
    """O maxLength do texto do turno no contrato versionado do commit, seguindo o $ref."""
    contrato = produto / "contrato" / "openapi.json"
    if not contrato.exists():
        return None
    dados = json.loads(contrato.read_text())
    esquemas = dados.get("components", {}).get("schemas", {})
    turno = dados.get("paths", {}).get("/conversas/{conversa_id}/turnos", {}).get("post", {})
    corpo = turno.get("requestBody", {}).get("content", {}).get("application/json", {})
    referencia = corpo.get("schema", {}).get("$ref", "")
    esquema = esquemas.get(referencia.rsplit("/", 1)[-1], {}) if referencia else {}
    return esquema.get("properties", {}).get("texto", {}).get("maxLength")


def gerar_base(argumentos) -> int:
    criada = base.gerar(argumentos.produto, argumentos.destino)
    print(json.dumps({"destino": str(argumentos.destino), **criada}, ensure_ascii=False))
    return 0


def rodar(argumentos) -> int:
    if not alvo_local(argumentos.url):
        print(f"[avaliar] recusado: {argumentos.url} não é loopback nem serviço do compose")
        return 2
    manifesto = json.loads(argumentos.cenarios.read_text())
    alvos = [c for c in manifesto["cenarios"] if c["conjunto"] in argumentos.conjuntos]
    if argumentos.banco_url:
        banco = avaliador.BancoPsycopg(argumentos.banco_url)
    elif argumentos.compose:
        banco = avaliador.BancoCompose(argumentos.compose, argumentos.produto)
    else:
        banco = None
    api = avaliador.Api(argumentos.url)
    origem = avaliador.Origem(argumentos.base)
    linhas = fixture.linhas_curadas(argumentos.base / "raw")
    limite = limite_da_mensagem(argumentos.produto)
    resultados, inicio = {}, time.monotonic()
    for cenario in alvos:
        execucao = avaliador.executar(cenario, api, limite, banco, origem)
        veredito = avaliador.julgar(cenario, execucao, linhas, argumentos.modelo_llm)
        resultados[cenario["id"]] = {
            **{chave: cenario[chave] for chave in ("conjunto", "categoria", "idioma", "familia")},
            "esperado_humano": cenario["esperado"]["humano"],
            **{
                chave: veredito.get(chave)
                for chave in (
                    "resolvido",
                    "seguro",
                    "encaminhou",
                    "envios",
                    "ms",
                    "rastreavel",
                    "auditado",
                    "na_primeira",
                    "pelo_llm",
                    "motivos",
                )
            },
        }
        marca = {True: "ok", False: "falhou", None: "sem julgamento"}[veredito["resolvido"]]
        print(f"[avaliar] {cenario['id']}: {marca} {veredito['motivos'][:2]}", flush=True)
    rodada = {
        "commit": argumentos.commit,
        "variante": argumentos.variante,
        "rodada": argumentos.rodada,
        "conjuntos": argumentos.conjuntos,
        "versao_dos_cenarios": manifesto["versao"],
        "versao_dos_dados": avaliador.versao_dos_dados(argumentos.base / "manifesto"),
        "quando": datetime.now(UTC).isoformat(timespec="seconds"),
        "duracao_s": round(time.monotonic() - inicio, 1),
        "cenarios": resultados,
    }
    argumentos.saida.mkdir(parents=True, exist_ok=True)
    nome = f"avaliacao-{argumentos.commit[:12]}-{argumentos.variante}-{argumentos.rodada}.json"
    (argumentos.saida / nome).write_text(json.dumps(rodada, ensure_ascii=False, indent=1))
    colunas = tabela.colunas(resultados)
    print(f"[avaliar] {argumentos.variante} rodada {argumentos.rodada}: ", end="")
    print(json.dumps({k: colunas[k] for k in ("resolucao_segura", "inseguros")}))
    print(f"[avaliar] gravado em {argumentos.saida / nome}")
    sem_llm = argumentos.exigir_llm and not colunas["turnos_pelo_llm"]
    return 2 if sem_llm else 0


def montar_tabela(argumentos) -> int:
    rodadas = [json.loads(Path(arquivo).read_text()) for arquivo in argumentos.rodadas]
    commits = {r["commit"] for r in rodadas}
    if len(commits) != 1:
        print(f"[avaliar] as rodadas são de commits diferentes: {sorted(commits)}")
        return 2
    montada = {
        "commit": commits.pop(),
        "versao_dos_cenarios": sorted({r["versao_dos_cenarios"] for r in rodadas}),
        "conjuntos": sorted({c for r in rodadas for c in r["conjuntos"]}),
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        **tabela.montar(rodadas),
    }
    argumentos.saida.mkdir(parents=True, exist_ok=True)
    nome = f"avaliacao-{montada['commit'][:12]}"
    (argumentos.saida / f"{nome}.json").write_text(
        json.dumps(montada, ensure_ascii=False, indent=1)
    )
    (argumentos.saida / f"{nome}.md").write_text(tabela.markdown(montada))
    print(tabela.markdown(montada))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="acao", required=True)
    p_base = sub.add_parser("base", help="gera a base de avaliação sintética")
    p_base.add_argument("--produto", type=Path, default=RAIZ)
    p_base.add_argument("--destino", type=Path, required=True)
    p_rodar = sub.add_parser("rodar", help="roda e julga os cenários numa variante")
    p_rodar.add_argument("--url", required=True, help="a API sob teste, com o /api")
    p_rodar.add_argument("--base", type=Path, required=True, help="a base carregada na stack")
    p_rodar.add_argument("--produto", type=Path, default=RAIZ, help="o checkout do commit")
    p_rodar.add_argument("--cenarios", type=Path, default=CENARIOS)
    p_rodar.add_argument("--conjuntos", nargs="+", default=["dev", "validacao"])
    p_rodar.add_argument("--variante", required=True, help="o INTERPRETADOR com que a stack subiu")
    p_rodar.add_argument("--rodada", type=int, default=1)
    p_rodar.add_argument("--commit", default="local")
    p_rodar.add_argument("--modelo-llm", default="qwen3:4b", help="o NAO_ENTENDI_MODELO da stack")
    p_rodar.add_argument(
        "--exigir-llm", action="store_true", help="2 se nenhum turno chegar ao LLM"
    )
    p_rodar.add_argument("--banco-url", help="a URL do banco da stack (num serviço do compose)")
    p_rodar.add_argument("--compose", help="o comando do compose da stack (no host)")
    p_rodar.add_argument("--saida", type=Path, default=RAIZ / "resultados")
    p_tabela = sub.add_parser("tabela", help="junta as rodadas na tabela")
    p_tabela.add_argument("rodadas", nargs="+")
    p_tabela.add_argument("--saida", type=Path, default=RAIZ / "resultados")
    argumentos = parser.parse_args(argv)
    acao = {"base": gerar_base, "rodar": rodar, "tabela": montar_tabela}[argumentos.acao]
    return acao(argumentos)


if __name__ == "__main__":
    sys.exit(main())
