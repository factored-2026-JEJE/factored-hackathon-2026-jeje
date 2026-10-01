"""Avaliação do leitor por mensagem (make avaliar-leitor): categorias e contagem por sistema.

Um leitor fixo (texto → fluxo e confiança definidos aqui) no lugar do e5; as regras e a decisão da
cascata são o código real, o mesmo da API.
"""

import pytest

from jeje.avaliacao_leitor import avaliar, classificar, main, tabela
from jeje.leitor.corpus import Exemplo
from jeje.leitor.modelo import Leitura as LidaDoModelo

VAGA = "apareceu um negócio esquisito na minha fatura"
OUTRA_VAGA = "tem uma coisa estranha acontecendo aqui"


class ModeloFixo:
    versao = "abcdef0123456789"

    def __init__(self, lidas: dict[str, tuple[str, float]]):
        self.lidas = lidas

    def ler(self, textos, _codificar):
        return [LidaDoModelo(*self.lidas.get(t, ("fora_de_escopo", 0.5))) for t in textos]


@pytest.mark.parametrize(
    ("lida", "esperada", "categorias"),
    [
        ("contestar", "contestar", ["certo"]),
        ("consultar", "contestar", ["errado"]),
        ("contestar", "fora_de_escopo", ["errado", "fora → ação"]),
        ("fraude", "fora_de_escopo", ["errado", "fora → ação"]),
        ("consultar", "fora_de_escopo", ["errado"]),
        ("desconhecida", "consultar", ["pede de novo"]),
        ("humano", "fraude", ["atendente"]),
    ],
)
def test_categorias_de_uma_mensagem(lida, esperada, categorias):
    assert classificar(lida, esperada) == categorias


def test_leitor_so_conta_onde_as_regras_nao_entendem_e_respeita_cada_limite():
    exemplos = [
        Exemplo("roubaram meu cartão", "relato_de_fraude", "pt"),  # as regras entendem
        Exemplo(VAGA, "abrir_disputa", "pt"),  # leitor com 0,85
        Exemplo(OUTRA_VAGA, "fora_de_escopo", "pt"),  # leitor erra com 0,95
    ]
    modelo = ModeloFixo({
        "roubaram meu cartão": ("abrir_disputa", 0.99),
        VAGA: ("abrir_disputa", 0.85),
        OUTRA_VAGA: ("abrir_disputa", 0.95),
    })  # fmt: skip
    c = avaliar(exemplos, modelo, None, limites=(0.8, 0.9))
    assert c["regras|pt"] == {"n": 3, "decidiu": 0, "certo": 1, "pede de novo": 2}
    assert c["leitor 0.8|pt"] == {"n": 3, "decidiu": 2, "certo": 2, "errado": 1, "fora → ação": 1}
    assert c["leitor 0.9|pt"] == {"n": 3, "decidiu": 1, "certo": 1, "pede de novo": 1,
                                  "errado": 1, "fora → ação": 1}  # fmt: skip


def test_tabela_mostra_cada_sistema_e_idioma_em_porcentagem():
    c = avaliar([Exemplo(VAGA, "abrir_disputa", "es")], ModeloFixo({VAGA: ("abrir_disputa", 0.9)}),
                None, limites=(0.8,))  # fmt: skip
    linhas = tabela(c).splitlines()
    assert linhas[0].split()[:3] == ["sistema", "idioma", "n"]
    assert linhas[1].split()[:4] == ["regras", "es", "1", "0.0%"]
    assert linhas[2].split()[:5] == ["leitor", "0.8", "es", "1", "100.0%"]


def test_cli_com_argumentos_demais_mostra_o_uso(capsys):
    assert main(["jeje.avaliacao_leitor", "a", "b"]) == 2
    assert "avaliar-leitor" in capsys.readouterr().err


class TfidfFixo:
    """O portão TF-IDF de Enzo com leituras fixas (texto → fluxo e confiança)."""

    def __init__(self, lidas: dict[str, tuple[str, float]]):
        self.lidas = lidas

    def fluxos(self, textos):
        return [self.lidas.get(t, ("fora_de_escopo", 0.5)) for t in textos]


def test_com_o_portao_tfidf_entram_a_cascata_dele_e_cada_leitor_sozinho():
    """PRD-009 e DEV-007: o componente aprendido contra a linha de base, no mesmo teste."""
    exemplos = [
        Exemplo("roubaram meu cartão", "relato_de_fraude", "pt"),  # as regras entendem
        Exemplo(VAGA, "abrir_disputa", "pt"),
    ]
    e5 = ModeloFixo({"roubaram meu cartão": ("abrir_disputa", 0.99), VAGA: ("abrir_disputa", 0.85)})
    tfidf = TfidfFixo(
        {"roubaram meu cartão": ("relato_de_fraude", 0.9), VAGA: ("fora_de_escopo", 0.95)}
    )
    c = avaliar(exemplos, e5, None, limites=(0.8,), tfidf=tfidf)
    assert c["leitor sozinho|pt"] == {"n": 2, "decidiu": 2, "certo": 1, "errado": 1}
    assert c["tfidf 0.8|pt"] == {"n": 2, "decidiu": 1, "certo": 1, "errado": 1}
    assert c["tfidf sozinho|pt"] == {"n": 2, "decidiu": 2, "certo": 1, "errado": 1}
