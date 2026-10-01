"""CLI do portão de intenção (estágio `intencao` da imagem do backend).

python -m jeje.intencao treinar <dir_corpus> <arquivo_modelo>   # baixa o corpus fixado e treina
"""

import sys
from pathlib import Path

from jeje.intencao.modelo import Classificador
from jeje.leitor import corpus, fontes


def treinar(dir_corpus: Path, arquivo_modelo: Path) -> Classificador:
    baixados = fontes.baixar(dir_corpus, corpus.arquivos())
    print(f"[intencao] corpus: {baixados} arquivo(s) baixado(s)", flush=True)
    classificador = Classificador.treinado(corpus.ler(dir_corpus))
    classificador.salvar(arquivo_modelo)
    m = classificador.metadados
    print(
        f"[intencao] modelo {m.versao[:12]} treinado com {m.exemplos_treino} exemplos", flush=True
    )
    for idioma, metricas in m.metricas_teste.items():
        print(
            f"[intencao] held-out {idioma}: {metricas.exemplos} exemplos, "
            f"acurácia {metricas.acuracia:.3f}, F1 macro {metricas.f1_macro:.3f}",
            flush=True,
        )
    return classificador


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] != "treinar":
        print(__doc__, file=sys.stderr)
        return 2
    try:
        treinar(Path(argv[2]), Path(argv[3]))
    except fontes.FonteInvalida as erro:
        print(f"[intencao] ERRO: {erro}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
