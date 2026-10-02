"""Vocabulário do corretor de digitação (DEV-060): as palavras do BANKING77 de treino em espanhol
e português, cada uma com quantas vezes aparece. É o vocabulário com que a validação mediu o
corretor (NOV-24): palavra com 2 ou mais ocorrências nunca é trocada, e a que aparece ao menos
uma vez não vira termo de fraude ("probado" não vira "robado").

python -m jeje.palavras <dir_corpus> <arquivo>
    baixa as traduções fixadas (sha256) e grava "palavra<TAB>ocorrências", uma por linha
"""

import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from jeje.interpretacao import normalizar
from jeje.leitor import corpus, fontes


def de_treino(tabelas: Iterable[corpus.Tabela] = corpus.BANKING77) -> tuple[corpus.Tabela, ...]:
    """As traduções ES e PT do treino oficial (o teste nunca entra no vocabulário)."""
    return tuple(t for t in tabelas if t.idioma in ("es", "pt") and t.particao == "treino")


def gerar(dir_corpus: Path, arquivo: Path, tabelas: Iterable[corpus.Tabela] | None = None) -> int:
    """Baixa (ou confere) as tabelas, conta as palavras normalizadas e grava a contagem."""
    tabelas = de_treino() if tabelas is None else tuple(tabelas)
    fontes.baixar(dir_corpus, tuple(t.arquivo for t in tabelas))
    contagem = Counter(
        palavra
        for tabela in tabelas
        for texto, _ in corpus._linhas(dir_corpus, tabela)
        for palavra in normalizar(texto).split()
    )
    linhas = [f"{palavra}\t{n}" for palavra, n in sorted(contagem.items())]
    arquivo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return len(linhas)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        total = gerar(Path(argv[1]), Path(argv[2]))
    except fontes.FonteInvalida as erro:
        print(f"[palavras] ERRO: {erro}", file=sys.stderr)
        return 1
    print(f"[palavras] {total} palavras em {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
