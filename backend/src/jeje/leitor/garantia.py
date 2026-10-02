"""Detector da garantia de encaminhamento da fraude (DEV-046: o passo 1 da V3 do NOV-33).

Uma cabeça própria sobre os vetores do e5 que o leitor já calcula, sem mexer no leitor (PRD-009):
regressão logística (a receita do leitor) nas classes consultar, contestar, fraude e fora de escopo,
treinada nas frases ES e PT do BANKING77 com o rótulo da validação (ambíguas fora, como os exemplos
do LLM) e nas 497 mensagens de golpe que a validação gerou no NOV-31, com a temperatura ajustada na
calibração. O limiar é por idioma: 1 menos o quantil conformal (alfa = 10%) de 1 - p(fraude) nas
fraudes da metade de calibração do teste do BANKING77, sorteada entre as posições de frases não
ambíguas, como no NOV-33. Os passos 2 e 3 (sinais de prevenção e o LLM confirmando) ficam na
conversa (jeje.garantia_fraude).
"""

import hashlib
import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import sklearn
from scipy.optimize import minimize_scalar
from sklearn.linear_model import LogisticRegression

from jeje.leitor import codificador, vizinhos
from jeje.leitor.corpus import Corpus, Exemplo
from jeje.leitor.modelo import PARAMETROS, ModeloInvalido, _softmax

CLASSES = ("consultar", "contestar", "fraude", "fora_de_escopo")
ALFA = 0.10
SEMENTE = 20261005  # a do NOV-15 e do NOV-33
IDIOMAS = ("es", "pt")
GOLPES = Path(__file__).with_name("golpes_nov31.json")


@dataclass(frozen=True)
class Mensagem:
    texto: str
    intencao: str
    idioma: str


def do_corpus(exemplos: Iterable[Exemplo]) -> list[Mensagem]:
    """As frases ES e PT do BANKING77 com o rótulo da validação; as ambíguas ficam fora."""
    saida = []
    for e in exemplos:
        if e.origem != "banking77" or e.idioma not in IDIOMAS:
            continue
        if (lida := vizinhos.intencao(e.intencao)) is not None:
            saida.append(Mensagem(e.texto, lida, e.idioma))
    return saida


def golpes(caminho: Path = GOLPES) -> list[Mensagem]:
    conteudo = json.loads(caminho.read_text(encoding="utf-8"))
    return [Mensagem(m["texto"], m["intencao"], m["idioma"]) for m in conteudo["mensagens"]]


def metade_de_calibracao(posicoes: Sequence[int], semente: int = SEMENTE) -> set[int]:
    """Metade das posições do teste, sorteada como no NOV-33; a outra metade fica para medir."""
    ordenadas = sorted(set(posicoes))
    sorteio = np.random.default_rng(semente).choice(ordenadas, len(ordenadas) // 2, replace=False)
    return {int(p) for p in sorteio}


def posicoes_de_calibracao(rotulos: dict[tuple[str, int], str | None]) -> set[int]:
    """A metade de calibração do teste, sorteada só entre as posições (idioma, posição) de frases
    não ambíguas (rótulo None), como no NOV-33."""
    return metade_de_calibracao([k for (_, k), r in rotulos.items() if r is not None])


def quantil(escores: Sequence[float], alfa: float) -> float:
    """O escore da posição teto((n + 1)(1 - alfa)), a correção de amostra finita. O estágio de
    treino da imagem só tem jeje.leitor, por isso não usa o da qual transação."""
    ordenados = sorted(escores)
    k = math.ceil((len(ordenados) + 1) * (1 - alfa))
    return ordenados[min(k, len(ordenados)) - 1]


@dataclass
class Garantia:
    logistica: LogisticRegression
    temperatura: float
    limiares: dict[str, float]  # por idioma: dispara com p(fraude) >= limiar
    versao: str

    FORMATO = 1

    def p_fraude(self, vetores: np.ndarray) -> np.ndarray:
        p = _softmax(self.logistica.decision_function(vetores) / self.temperatura)
        return p[:, list(self.logistica.classes_).index("fraude")]

    @classmethod
    def treinada(
        cls,
        corpus: Corpus,
        codificar: codificador.Codificador,
        versao_: str,
        geradas: Sequence[Mensagem],
    ) -> "Garantia":
        treino = do_corpus(corpus.treino) + list(geradas)
        logistica = LogisticRegression(**PARAMETROS).fit(
            codificar([m.texto for m in treino]), [m.intencao for m in treino]
        )
        if sorted(logistica.classes_) != sorted(CLASSES):
            raise ModeloInvalido(f"treino da garantia sem as classes {sorted(CLASSES)}")
        calibracao = do_corpus(corpus.calibracao)
        z = logistica.decision_function(codificar([m.texto for m in calibracao]))
        alvo = np.array([list(logistica.classes_).index(m.intencao) for m in calibracao])

        def perda(t: float) -> float:
            return float(-np.log(_softmax(z / t)[np.arange(len(alvo)), alvo] + 1e-12).mean())

        temperatura = float(minimize_scalar(perda, bounds=(0.05, 20), method="bounded").x)
        garantia = cls(logistica, temperatura, {}, versao_)
        # A posição de cada frase do teste no seu idioma, com o rótulo da validação.
        teste = {i: [e for e in corpus.teste if e.idioma == i] for i in IDIOMAS}
        rotulos = {(i, k): vizinhos.intencao(e.intencao) for i, es in teste.items()
                   for k, e in enumerate(es)}  # fmt: skip
        sorteadas = posicoes_de_calibracao(rotulos)
        for idioma, exemplos in teste.items():
            fraudes = [e.texto for k, e in enumerate(exemplos)
                       if k in sorteadas and rotulos[idioma, k] == "fraude"]  # fmt: skip
            escores = 1 - garantia.p_fraude(codificar(fraudes))
            garantia.limiares[idioma] = round(1 - quantil(escores.tolist(), ALFA), 4)
        return garantia

    def salvar(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"formato": self.FORMATO, "logistica": self.logistica,
                     "temperatura": self.temperatura, "limiares": self.limiares,
                     "versao": self.versao}, caminho)  # fmt: skip

    @classmethod
    def carregar(cls, caminho: Path) -> "Garantia":
        # Artefato produzido pelo próprio build (joblib/pickle): nunca carregar de origem externa.
        if not caminho.is_file():
            raise ModeloInvalido(f"artefato ausente: {caminho}")
        conteudo = joblib.load(caminho)
        if not isinstance(conteudo, dict) or conteudo.get("formato") != cls.FORMATO:
            raise ModeloInvalido(f"formato desconhecido em {caminho}")
        garantia = cls(conteudo["logistica"], conteudo["temperatura"], conteudo["limiares"],
                       conteudo["versao"])  # fmt: skip
        if sorted(garantia.limiares) != sorted(IDIOMAS):
            raise ModeloInvalido("garantia sem o limiar de algum idioma")
        return garantia


def versao(leitor: str, geradas: Path = GOLPES) -> str:
    """A versão do leitor (dados, pesos e mapeamentos), as mensagens geradas e os parâmetros."""
    entrada = {
        "leitor": leitor,
        "rotulos": vizinhos.versao(leitor),
        "geradas": hashlib.sha256(geradas.read_bytes()).hexdigest(),
        "parametros": PARAMETROS,
        "alfa": ALFA,
        "semente": SEMENTE,
        "sklearn": sklearn.__version__,
    }
    return hashlib.sha256(json.dumps(entrada, sort_keys=True).encode()).hexdigest()
