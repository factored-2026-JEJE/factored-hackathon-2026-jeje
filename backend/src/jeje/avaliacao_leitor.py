"""Avaliação do leitor por mensagem (make avaliar-leitor, fora do gate; precisa da stack no ar).

No teste oficial do BANKING77 (nunca visto no treino), em espanhol e português, compara o que a
conversa receberia de cada mensagem: só as regras, e a cascata com o leitor em alguns limites de
confiança. A decisão da cascata é a mesma da API (`interpretacao_leitor.em_cascata`). Por mensagem:

- certo: a intenção lida é a do rótulo (consultar, contestar, fraude, fora_de_escopo);
- errado: outra intenção (a conversa segue pelo fluxo errado ou recusa);
- pede de novo: não entendida (a conversa pede para reformular);
- atendente: pedido de atendente lido pelas regras;
- fora → ação: pedido fora de escopo lido como contestação ou fraude (o erro que o limite evita).

Com o artefato do portão TF-IDF de Enzo (INTENCAO_MODELO, PRD-009), entram também a cascata com ele
e cada leitor sozinho, sem as regras: o componente aprendido contra a linha de base (DEV-007).

    python -m jeje.avaliacao_leitor [dir_corpus]    # baixa o teste fixado (~4 MB) se faltar
"""

import sys
import tempfile
import time
from collections import Counter
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from jeje.config import Settings
from jeje.intencao.modelo import Classificador, ModeloInvalido
from jeje.interpretacao import interpretar
from jeje.interpretacao_leitor import em_cascata
from jeje.interpretacao_modelo import entendida
from jeje.leitor import corpus, fontes
from jeje.leitor.codificador import E5, Codificador
from jeje.leitor.corpus import Exemplo
from jeje.leitor.fluxos import LEITURA_DO_FLUXO
from jeje.leitor.modelo import Leitura, ModeloLeitor

LIMITES = (0.7, 0.8, 0.9)
HOJE = date(2026, 6, 30)
CATEGORIAS = ("certo", "errado", "pede de novo", "atendente", "fora → ação")


def classificar(lida: str, esperada: str) -> list[str]:
    """Categorias de uma mensagem, dada a intenção lida e a do rótulo."""
    if lida == "desconhecida":
        return ["pede de novo"]
    if lida == "humano":
        return ["atendente"]
    if lida == esperada:
        return ["certo"]
    return ["errado"] + (["fora → ação"] if esperada == "fora_de_escopo" and lida in
                         ("contestar", "fraude") else [])  # fmt: skip


def avaliar(
    exemplos: Sequence[Exemplo],
    modelo: ModeloLeitor,
    codificar: Codificador,
    limites: Sequence[float] = LIMITES,
    tfidf: Classificador | None = None,
) -> dict[str, Counter]:
    """Contagens por sistema ("regras", "leitor 0.8", "leitor sozinho", "tfidf 0.8", ...) e idioma:
    {f"{sistema}|{idioma}": ...}. "decidiu" conta as mensagens em que o leitor decidiu no lugar das
    regras; sozinho, ele decide todas."""
    textos = [e.texto for e in exemplos]
    leitores = {"leitor": modelo.ler(textos, codificar)}
    if tfidf is not None:
        leitores["tfidf"] = [Leitura(fluxo, confianca) for fluxo, confianca in tfidf.fluxos(textos)]
    contagens: dict[str, Counter] = {}
    for i, e in enumerate(exemplos):
        esperada = LEITURA_DO_FLUXO[e.fluxo][0]
        regras = interpretar(e.texto, e.idioma, HOJE)
        sistemas = {"regras": (regras.intencao, False)}
        for nome, lidas in leitores.items():
            for limite in limites:
                if entendida(regras):
                    sistemas[f"{nome} {limite}"] = (regras.intencao, False)
                else:
                    lido, decidiu = em_cascata(regras, lidas[i], limite)
                    sistemas[f"{nome} {limite}"] = (lido.intencao, decidiu)
            sistemas[f"{nome} sozinho"] = (LEITURA_DO_FLUXO[lidas[i].fluxo][0], True)
        for sistema, (intencao, decidiu) in sistemas.items():
            c = contagens.setdefault(f"{sistema}|{e.idioma}", Counter())
            c["n"] += 1
            c["decidiu"] += decidiu
            c.update(classificar(intencao, esperada))
    return contagens


def tabela(contagens: dict[str, Counter]) -> str:
    linhas = [f"{'sistema':14} {'idioma':6} {'n':>5} "
              + " ".join(f"{c:>12}" for c in (*CATEGORIAS, "leitor decidiu"))]  # fmt: skip
    for chave, c in contagens.items():
        sistema, idioma = chave.split("|")
        valores = [c[k] / c["n"] for k in (*CATEGORIAS, "decidiu")]
        linhas.append(f"{sistema:14} {idioma:6} {c['n']:5d} "
                      + " ".join(f"{v:12.1%}" for v in valores))  # fmt: skip
    return "\n".join(linhas)


def main(argv: list[str]) -> int:
    if len(argv) > 2:
        print(__doc__, file=sys.stderr)
        return 2
    config = Settings()
    destino = Path(argv[1]) if len(argv) == 2 else Path(tempfile.gettempdir()) / "leitor-avaliacao"
    try:
        fontes.baixar(destino, tuple(t.arquivo for t in corpus.BANKING77))
        # Só o BANKING77: o MInDS-14 entra só no treino (e a imagem da API não lê parquet).
        banking77 = corpus._banking77(destino, corpus.BANKING77)
        teste = [e for e in banking77["teste"] if e.idioma in ("es", "pt")]
        modelo = ModeloLeitor.carregar(config.leitor_modelo)
        codificar = E5(config.leitor_e5)
    except fontes.FonteInvalida as erro:
        print(f"[avaliacao] ERRO: {erro}", file=sys.stderr)
        return 1
    try:
        tfidf = Classificador.carregar(config.intencao_modelo)
    except ModeloInvalido as erro:
        print(f"[avaliacao] sem o portão TF-IDF: {erro}", file=sys.stderr)
        tfidf = None
    inicio = time.perf_counter()
    contagens = avaliar(teste, modelo, codificar, tfidf=tfidf)
    ms = (time.perf_counter() - inicio) * 1000 / len(teste)
    print(f"# Leitor {modelo.versao[:12]} no teste do BANKING77 (es+pt, {len(teste)} mensagens, "
          f"nunca vistas no treino); limite da API: {config.leitor_limite}")  # fmt: skip
    print(tabela(contagens))
    print(f"\n~{ms:.1f} ms por mensagem (regras + leitores em lote, CPU)")
    if tfidf is not None:
        print(f"Portão TF-IDF de Enzo {tfidf.metadados.versao[:12]}, no mesmo teste")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
