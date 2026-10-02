"""Corpus rotulado do leitor: BANKING77 (inglês + traduções revisadas ES e PT) e MInDS-14 (fala
real transcrita, es-ES e pt-PT). Licenças: BANKING77 e MInDS-14 (PolyAI) e traduções c2d-usp, todas
CC-BY-4.0 (atribuição no README).

BANKING77: o inglês traz a intenção; a tradução ES tem as mesmas linhas na mesma ordem, mas a
coluna de rótulo é inconsistente (629 grafias para 77 intenções), então herda a intenção do inglês
pela posição; a PT tem rótulos limpos, traduzidos, mapeados para o inglês pelas linhas alinhadas do
treino. O split treino/teste é o oficial: a mesma frase nunca está nos dois lados em idioma nenhum.

MInDS-14 entra só no treino (as categorias que o BANKING77 não tem: problema com o cartão,
bloqueio, ver transações). A calibração da confiança separa 20% das frases do treino do BANKING77,
com as três línguas de cada frase juntas (a tradução nunca fica do outro lado).
"""

import csv
import random
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from jeje.leitor.fluxos import Fluxo, fluxo_do_banking77, fluxo_do_minds14
from jeje.leitor.fontes import Arquivo, FonteInvalida, exigir

Idioma = Literal["en", "es", "pt"]
Particao = Literal["treino", "teste"]

_POLYAI = (
    "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/"
    "57ec275d8078af65b7731c2a98be812d844a6d6b/banking_data"
)
_ES = "https://huggingface.co/datasets/c2d-usp/banking77-es-la/resolve/11f2c4d028e7df4d5e8e6ad36977cf9bf10cb666"
_PT = "https://huggingface.co/datasets/c2d-usp/banking77-pt-br/resolve/85f51c4a36c69482fae32ec31afec784f9722a7e"
_MINDS = "https://huggingface.co/datasets/PolyAI/minds14/resolve/40ce77cb32a384e4d50a568e1ec39ac804019d33"


class CorpusInvalido(FonteInvalida):
    """Fonte ausente, corrompida ou com rótulos que não se alinham."""


@dataclass(frozen=True)
class Tabela:
    """CSV do BANKING77 (ou tradução) fixado, e as colunas de texto e rótulo."""

    idioma: Idioma
    particao: Particao
    arquivo: Arquivo
    coluna_texto: str
    coluna_rotulo: str


def _csv(idioma, particao, url, tamanho, sha256, texto, rotulo) -> Tabela:
    return Tabela(idioma, particao, Arquivo(f"banking77/{idioma}_{particao}.csv", url, tamanho,
                                            sha256), texto, rotulo)  # fmt: skip


BANKING77: tuple[Tabela, ...] = (
    _csv("en", "treino", f"{_POLYAI}/train.csv", 839073,
         "b06e26ac675513959a63135f11b94ea7786ed02da65db93a5650d8838cbc664b", "text", "category"),
    _csv("en", "teste", f"{_POLYAI}/test.csv", 239961,
         "d12d6e3bc4c3103966ae786dc435913c0c563dfa328f5a3646d0e62cfeeb474d", "text", "category"),
    _csv("es", "treino", f"{_ES}/banking77-es-la-train.csv", 981097,
         "ecad51042baedddadeffe250bddcf964deeabf33af574afa1f667816f91ad164", "frase", "rotulo"),
    _csv("es", "teste", f"{_ES}/banking77-es-la-test.csv", 281377,
         "9eaa91421af15d979f8ba434008228a53593c6eb8329d43ee3dcc97e31eea72f", "frase", "rotulo"),
    _csv("pt", "treino", f"{_PT}/train.csv", 1131439,
         "ba4f3476981f1d5f2a74199dc0af6bf8d793c939546cdb543bf1d38073ba9d33", "frase", "rotulo"),
    _csv("pt", "teste", f"{_PT}/test.csv", 325683,
         "37a6f37ceae0d342e15d71cbd944c68d4e26278c396b31587d5eb2a557eeafca", "frase", "rotulo"),
)  # fmt: skip

# MInDS-14: um parquet por língua (com o áudio; só `path`, `transcription` e `intent_class` são
# lidos). `intent_class` indexa as 14 intenções em ordem alfabética (features do dataset).
MINDS14: tuple[tuple[Idioma, Arquivo], ...] = (
    ("es", Arquivo("minds14/es-ES.parquet", f"{_MINDS}/es-ES/train-00000-of-00001.parquet",
                   39069577, "989bf2f90676a5eb5852fe785a03b1d9b97763e0febbd0fd0a3f489afd83badf")),
    ("pt", Arquivo("minds14/pt-PT.parquet", f"{_MINDS}/pt-PT/train-00000-of-00001.parquet",
                   51738310, "b2a62e1cf0fefc1ce7f0045fb3991b1ccb0f0b5b394c490ce05e8878a15a0cb1")),
)  # fmt: skip
INTENCOES_MINDS14 = (
    "abroad", "address", "app_error", "atm_limit", "balance", "business_loan", "card_issues",
    "cash_deposit", "direct_debit", "freeze", "high_value_payment", "joint_account",
    "latest_transactions", "pay_bill",
)  # fmt: skip


def arquivos(banking77=BANKING77, minds14=MINDS14) -> tuple[Arquivo, ...]:
    return tuple(t.arquivo for t in banking77) + tuple(a for _, a in minds14)


@dataclass(frozen=True)
class Exemplo:
    texto: str
    fluxo: Fluxo
    idioma: Idioma
    origem: Literal["banking77", "minds14"] = "banking77"
    intencao: str = ""  # o rótulo do corpus (intenção em inglês), de onde o fluxo veio


@dataclass(frozen=True)
class Corpus:
    treino: list[Exemplo]  # BANKING77 (80% das frases) + MInDS-14 inteiro
    calibracao: list[Exemplo]  # BANKING77, 20% das frases do treino oficial, nas três línguas
    teste: list[Exemplo]  # BANKING77, teste oficial
    # BANKING77, o treino oficial inteiro na ordem do arquivo (en, es, pt): a garantia de fraude
    # refaz nele a divisão pré-registrada da validação (jeje.leitor.garantia).
    oficial: list[Exemplo] = field(default_factory=list)


def _linhas(destino: Path, tabela: Tabela) -> list[tuple[str, str]]:
    """(texto, rótulo) na ordem do arquivo; linhas sem texto (há 2 no fim do teste PT) saem."""
    try:
        caminho = exigir(destino, tabela.arquivo)
    except FonteInvalida as erro:
        raise CorpusInvalido(str(erro)) from erro
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        return [
            (linha[tabela.coluna_texto].strip(), linha[tabela.coluna_rotulo].strip())
            for linha in csv.DictReader(arquivo)
            if (linha.get(tabela.coluna_texto) or "").strip()
        ]


def _banking77(destino: Path, tabelas: Iterable[Tabela]) -> dict[Particao, list[Exemplo]]:
    linhas = {(t.idioma, t.particao): _linhas(destino, t) for t in tabelas}
    intencoes = {p: [rotulo for _, rotulo in linhas["en", p]] for p in ("treino", "teste")}

    for particao in ("treino", "teste"):
        if len(linhas["es", particao]) != len(intencoes[particao]):
            raise CorpusInvalido(f"ES {particao} não tem as mesmas linhas do inglês")
    if len(linhas["pt", "treino"]) != len(intencoes["treino"]):
        raise CorpusInvalido("PT treino não tem as mesmas linhas do inglês")

    # Rótulo PT → intenção em inglês, aprendido das linhas alinhadas; ambiguidade é erro.
    intencao_pt: dict[str, str] = {}
    for (_, rotulo), intencao in zip(linhas["pt", "treino"], intencoes["treino"], strict=True):
        if intencao_pt.setdefault(rotulo, intencao) != intencao:
            raise CorpusInvalido(f"rótulo PT {rotulo!r} corresponde a mais de uma intenção")

    def exemplos(particao: Particao) -> list[Exemplo]:
        saida = []
        for idioma in ("en", "es"):
            saida += [
                Exemplo(texto, fluxo_do_banking77(intencao), idioma, intencao=intencao)
                for (texto, _), intencao in zip(
                    linhas[idioma, particao], intencoes[particao], strict=True
                )
            ]
        for texto, rotulo in linhas["pt", particao]:
            if rotulo not in intencao_pt:
                raise CorpusInvalido(f"rótulo PT desconhecido no {particao}: {rotulo!r}")
            intencao = intencao_pt[rotulo]
            saida.append(Exemplo(texto, fluxo_do_banking77(intencao), "pt", intencao=intencao))
        return saida

    return {"treino": exemplos("treino"), "teste": exemplos("teste")}


def _minds14(destino: Path, fontes: Iterable[tuple[Idioma, Arquivo]]) -> list[Exemplo]:
    import pyarrow.parquet as pq  # só o treino (estágio `modelo` da imagem) lê parquet

    saida = []
    for idioma, arquivo in fontes:
        try:
            caminho = exigir(destino, arquivo)
        except FonteInvalida as erro:
            raise CorpusInvalido(str(erro)) from erro
        colunas = pq.read_table(caminho, columns=["path", "transcription", "intent_class"])
        for trilha, texto, classe in zip(*colunas.to_pydict().values(), strict=True):
            intencao = INTENCOES_MINDS14[classe]
            # O caminho do áudio também traz a intenção ("…~CARD_ISSUES/…"): as duas batem.
            if f"~{intencao.upper()}/" not in trilha:
                raise CorpusInvalido(f"MInDS-14 {idioma}: rótulo {intencao} não bate com {trilha}")
            if texto.strip():
                fluxo = fluxo_do_minds14(intencao)
                saida.append(Exemplo(texto.strip(), fluxo, idioma, "minds14", intencao))
    return saida


def separar_calibracao(
    treino: list[Exemplo], fracao: float = 0.2, semente: int = 0
) -> tuple[list[Exemplo], list[Exemplo]]:
    """Treino alinhado (blocos en, es, pt com a mesma frase na mesma posição): sorteia posições,
    e as três línguas de cada posição sorteada vão juntas para a calibração."""
    posicoes, contagem = [], {"en": 0, "es": 0, "pt": 0}
    for e in treino:
        posicoes.append(contagem[e.idioma])
        contagem[e.idioma] += 1
    sorteadas = set(
        random.Random(semente).sample(range(contagem["en"]), int(contagem["en"] * fracao))
    )
    fica = [e for e, i in zip(treino, posicoes, strict=True) if i not in sorteadas]
    calibracao = [e for e, i in zip(treino, posicoes, strict=True) if i in sorteadas]
    return fica, calibracao


def ler(destino: Path, banking77=BANKING77, minds14=MINDS14) -> Corpus:
    b77 = _banking77(destino, banking77)
    treino, calibracao = separar_calibracao(b77["treino"])
    return Corpus(treino=treino + _minds14(destino, minds14), calibracao=calibracao,
                  teste=b77["teste"], oficial=b77["treino"])  # fmt: skip
