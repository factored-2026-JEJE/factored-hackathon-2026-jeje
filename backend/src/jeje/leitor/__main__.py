"""CLI do leitor (estágio `modelo` da imagem do backend).

python -m jeje.leitor treinar <dir_corpus> <dir_e5> <arquivo_modelo>
    baixa o corpus e os pesos do e5 fixados, treina e grava o artefato
"""

import sys
from pathlib import Path

from jeje.leitor import codificador, corpus, fontes
from jeje.leitor.modelo import ModeloLeitor, versao


def treinar(dir_corpus: Path, dir_e5: Path, arquivo_modelo: Path) -> ModeloLeitor:
    baixados = fontes.baixar(dir_corpus, corpus.arquivos())
    print(f"[leitor] corpus: {baixados} arquivo(s) baixado(s)", flush=True)
    baixados = fontes.baixar(dir_e5, codificador.PESOS)
    print(f"[leitor] e5 {codificador.REVISAO[:12]}: {baixados} arquivo(s) baixado(s)", flush=True)
    lido = corpus.ler(dir_corpus)
    print(f"[leitor] treino {len(lido.treino)}, calibração {len(lido.calibracao)}, "
          f"teste {len(lido.teste)} exemplos", flush=True)  # fmt: skip
    modelo = ModeloLeitor.treinado(lido, codificador.E5(dir_e5), versao(corpus.arquivos()))
    modelo.salvar(arquivo_modelo)
    print(f"[leitor] modelo {modelo.versao[:12]}, temperatura {modelo.temperatura:.3f}, "
          f"teste {modelo.metricas}", flush=True)  # fmt: skip
    return modelo


def main(argv: list[str]) -> int:
    if len(argv) != 5 or argv[1] != "treinar":
        print(__doc__, file=sys.stderr)
        return 2
    try:
        treinar(Path(argv[2]), Path(argv[3]), Path(argv[4]))
    except fontes.FonteInvalida as erro:
        print(f"[leitor] ERRO: {erro}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
