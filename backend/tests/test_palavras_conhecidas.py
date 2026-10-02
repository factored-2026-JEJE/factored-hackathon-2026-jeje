"""O vocabulário do corretor de digitação (DEV-060): as palavras normalizadas das traduções ES e PT
do treino do BANKING77, com a contagem; o teste e o inglês nunca entram."""

from jeje.dados.manifesto import sha256_de
from jeje.leitor import corpus, fontes
from jeje.palavras import de_treino, gerar


def tabela(raiz, idioma, particao, frases) -> corpus.Tabela:
    nome = f"banking77/{idioma}_{particao}.csv"
    caminho = raiz / nome
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("frase,rotulo\n" + "".join(f"{f},x\n" for f in frases), encoding="utf-8")
    arquivo = fontes.Arquivo(
        nome, "http://nao-e-baixado", caminho.stat().st_size, sha256_de(caminho)
    )
    return corpus.Tabela(idioma, particao, arquivo, "frase", "rotulo")


def test_vocabulario_conta_as_palavras_das_traducoes_de_treino(tmp_path):
    tabelas = [
        tabela(tmp_path, "es", "treino", ["Perdí mi tarjeta", "mi TARJETA"]),
        tabela(tmp_path, "pt", "treino", ["meu cartão"]),
        tabela(tmp_path, "es", "teste", ["nunca entra"]),
        tabela(tmp_path, "en", "treino", ["never"]),
    ]
    total = gerar(tmp_path, tmp_path / "saida.txt", de_treino(tabelas))
    linhas = (tmp_path / "saida.txt").read_text(encoding="utf-8").splitlines()
    assert linhas == ["cartao\t1", "meu\t1", "mi\t2", "perdi\t1", "tarjeta\t2"]
    assert total == 5
