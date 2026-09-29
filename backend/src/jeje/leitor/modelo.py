"""Classificador do leitor: regressão logística sobre os vetores do e5, com a confiança calibrada.

A confiança é a probabilidade do fluxo mais provável depois do ajuste de temperatura (Guo et al.
2017) na calibração: "0,8" quer dizer que, entre as mensagens lidas com 0,8, cerca de 80% estão
certas. É sobre ela que o limite da cascata (0,8, ACH-028) age.

O artefato guarda só números (coeficientes, temperatura, métricas) e a versão: o codificador não
entra no arquivo e é passado a quem lê.
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import sklearn
from scipy.optimize import minimize_scalar
from sklearn.linear_model import LogisticRegression

from jeje.leitor import codificador
from jeje.leitor.corpus import Corpus, Exemplo
from jeje.leitor.fluxos import FLUXO_DO_BANKING77, FLUXO_DO_MINDS14, FLUXOS, Fluxo
from jeje.leitor.fontes import Arquivo

PARAMETROS = {"C": 10.0, "class_weight": "balanced", "max_iter": 3000}


class ModeloInvalido(Exception):
    """Artefato ausente, de outra versão do formato ou com fluxos diferentes dos do código."""


def _softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def versao(fontes: Sequence[Arquivo], pesos: Sequence[Arquivo] = codificador.PESOS) -> str:
    """sha256 das entradas que determinam o modelo: dados, pesos do e5, mapeamentos, parâmetros e
    sklearn. Mesmas entradas, mesma versão, em qualquer máquina."""
    entrada = {
        "fontes": [f.sha256 for f in fontes],
        "pesos": [p.sha256 for p in pesos],
        "mapeamento": [FLUXO_DO_BANKING77, FLUXO_DO_MINDS14],
        "parametros": PARAMETROS,
        "sklearn": sklearn.__version__,
    }
    return hashlib.sha256(json.dumps(entrada, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Leitura:
    fluxo: Fluxo
    confianca: float


@dataclass
class ModeloLeitor:
    logistica: LogisticRegression
    temperatura: float
    versao: str
    metricas: dict  # acurácia no teste do BANKING77 por idioma e na faixa da cascata (>= 0,8)

    FORMATO = 1

    @property
    def fluxos(self) -> list[Fluxo]:
        return [str(c) for c in self.logistica.classes_]

    def probabilidades(self, vetores: np.ndarray) -> np.ndarray:
        return _softmax(self.logistica.decision_function(vetores) / self.temperatura)

    def ler(self, textos: Sequence[str], codificar: codificador.Codificador) -> list[Leitura]:
        p = self.probabilidades(codificar(list(textos)))
        melhores = p.argmax(axis=1)
        return [Leitura(self.fluxos[k], round(float(p[i, k]), 4)) for i, k in enumerate(melhores)]

    @classmethod
    def treinado(
        cls, corpus: Corpus, codificar: codificador.Codificador, versao_: str
    ) -> "ModeloLeitor":
        def vetores(exemplos: list[Exemplo]) -> np.ndarray:
            return codificar([e.texto for e in exemplos])

        logistica = LogisticRegression(**PARAMETROS).fit(
            vetores(corpus.treino), [e.fluxo for e in corpus.treino]
        )
        faltando = set(FLUXOS) - set(logistica.classes_)
        if faltando:
            raise ModeloInvalido(f"treino sem exemplos de {sorted(faltando)}")
        modelo = cls(logistica, 1.0, versao_, {})
        z = logistica.decision_function(vetores(corpus.calibracao))
        y = np.array([modelo.fluxos.index(e.fluxo) for e in corpus.calibracao])

        def perda(t: float) -> float:
            p = _softmax(z / t)
            return float(-np.log(p[np.arange(len(y)), y] + 1e-12).mean())

        modelo.temperatura = float(minimize_scalar(perda, bounds=(0.05, 20), method="bounded").x)
        modelo.metricas = modelo._medir(corpus.teste, codificar)
        return modelo

    def _medir(self, teste: list[Exemplo], codificar: codificador.Codificador) -> dict:
        lidas = self.ler([e.texto for e in teste], codificar)
        certo = np.array([lida.fluxo == e.fluxo for lida, e in zip(lidas, teste, strict=True)])
        confianca = np.array([lida.confianca for lida in lidas])
        metricas = {}
        for idioma in sorted({e.idioma for e in teste}):
            m = np.array([e.idioma == idioma for e in teste])
            metricas[f"acuracia_{idioma}"] = round(float(certo[m].mean()), 4)
        acima = confianca >= 0.8
        metricas["cobertura_0_8"] = round(float(acima.mean()), 4)
        metricas["acuracia_0_8"] = round(float(certo[acima].mean()), 4) if acima.any() else None
        return metricas

    def salvar(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"formato": self.FORMATO, "logistica": self.logistica,
                     "temperatura": self.temperatura, "versao": self.versao,
                     "metricas": self.metricas}, caminho)  # fmt: skip

    @classmethod
    def carregar(cls, caminho: Path) -> "ModeloLeitor":
        # Artefato produzido pelo próprio build (joblib/pickle): nunca carregar de origem externa.
        if not caminho.is_file():
            raise ModeloInvalido(f"artefato ausente: {caminho}")
        conteudo = joblib.load(caminho)
        if not isinstance(conteudo, dict) or conteudo.get("formato") != cls.FORMATO:
            raise ModeloInvalido(f"formato desconhecido em {caminho}")
        modelo = cls(conteudo["logistica"], conteudo["temperatura"], conteudo["versao"],
                     conteudo["metricas"])  # fmt: skip
        if sorted(modelo.fluxos) != sorted(FLUXOS):
            raise ModeloInvalido("fluxos do artefato diferentes dos do código")
        return modelo
