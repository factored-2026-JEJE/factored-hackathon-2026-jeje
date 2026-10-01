"""Modelo do portão: TF-IDF de n-gramas de caracteres + regressão logística.

Escrito por Enzo (tag `arquivo/intencao-classificador`, commit b09cdc4), que o escolheu por
comparação no mesmo held-out: empatou ou superou embeddings multilíngues (e5-base) e superou com
folga um LLM local prompted (Qwen3-1.7B), a ~1 ms por mensagem, com probabilidades e sinais
inspecionáveis. N-gramas de caracteres toleram erro de digitação e acento, e ES/PT compartilham
radicais. Incorporado no main em 01/10 (PRD-009, item 1) como componente aprendido de comparação ao
lado do leitor e5, que veio depois, também de Enzo: mesmo corpus e mesmos fluxos do leitor
(`jeje.leitor.corpus` e `jeje.leitor.fluxos`, que sucederam o corpus e os fluxos deste portão), e a
comparação no mesmo teste do BANKING77 (`make avaliar-leitor`).

O artefato leva os metadados de linhagem (fontes, versões, métricas por idioma); a versão é o
sha256 de tudo que determina o modelo, então treinar de novo com as mesmas entradas dá a mesma.
"""

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import joblib
import numpy as np
import sklearn
from pydantic import BaseModel
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import Pipeline

from jeje.leitor.corpus import Corpus, Exemplo, arquivos
from jeje.leitor.fluxos import FLUXO_DO_BANKING77, FLUXO_DO_MINDS14, FLUXOS, Fluxo
from jeje.leitor.fontes import Arquivo

PARAMETROS = {
    "tfidf": {"analyzer": "char_wb", "ngram_range": (2, 5), "min_df": 2, "sublinear_tf": True},
    "logistica": {"max_iter": 3000, "class_weight": "balanced"},
}


class ModeloInvalido(Exception):
    """Artefato ausente, corrompido ou de outra versão do formato."""


class MetricasIdioma(BaseModel):
    exemplos: int
    acuracia: float
    f1_macro: float


class Metadados(BaseModel):
    versao: str
    sklearn: str
    fontes: list[str]  # url@sha256 de cada fonte do corpus
    exemplos_treino: int
    metricas_teste: dict[str, MetricasIdioma]  # por idioma do held-out oficial


class Probabilidade(BaseModel):
    fluxo: Fluxo
    probabilidade: float


class Previsao(BaseModel):
    fluxo: Fluxo
    confianca: float
    probabilidades: list[Probabilidade]  # todos os fluxos, da mais para a menos provável
    sinais: list[str]  # n-gramas que mais puxaram para o fluxo escolhido ("_" = borda de palavra)
    modelo: str  # versão do modelo que respondeu


def treinar(exemplos: list[Exemplo]) -> Pipeline:
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(**PARAMETROS["tfidf"])),
            ("logistica", LogisticRegression(**PARAMETROS["logistica"])),
        ]
    ).fit([e.texto for e in exemplos], [e.fluxo for e in exemplos])


def avaliar(pipeline: Pipeline, exemplos: list[Exemplo]) -> dict[str, MetricasIdioma]:
    metricas = {}
    for idioma in sorted({e.idioma for e in exemplos}):
        grupo = [e for e in exemplos if e.idioma == idioma]
        esperado = [e.fluxo for e in grupo]
        previsto = pipeline.predict([e.texto for e in grupo])
        f1 = f1_score(esperado, previsto, labels=list(FLUXOS), average="macro", zero_division=0)
        metricas[idioma] = MetricasIdioma(
            exemplos=len(grupo),
            acuracia=round(float(accuracy_score(esperado, previsto)), 4),
            f1_macro=round(float(f1), 4),
        )
    return metricas


def versao(fontes: Sequence[Arquivo] = ()) -> str:
    """sha256 das entradas que determinam o modelo: dados, mapeamento, parâmetros e sklearn."""
    entrada = {
        "fontes": [f.sha256 for f in (fontes or arquivos())],
        "mapeamento": {"banking77": FLUXO_DO_BANKING77, "minds14": FLUXO_DO_MINDS14},
        "parametros": PARAMETROS,
        "sklearn": sklearn.__version__,
    }
    return hashlib.sha256(json.dumps(entrada, sort_keys=True, default=str).encode()).hexdigest()


class Classificador:
    def __init__(self, pipeline: Pipeline, metadados: Metadados):
        self.pipeline = pipeline
        self.metadados = metadados
        self._tfidf: TfidfVectorizer = pipeline.named_steps["tfidf"]
        self._logistica: LogisticRegression = pipeline.named_steps["logistica"]
        self._ngramas = self._tfidf.get_feature_names_out()

    @classmethod
    def treinado(cls, corpus: Corpus, fontes: Sequence[Arquivo] = ()) -> "Classificador":
        fontes = tuple(fontes or arquivos())
        pipeline = treinar(corpus.treino)
        metadados = Metadados(
            versao=versao(fontes),
            sklearn=sklearn.__version__,
            fontes=[f"{f.url}@{f.sha256}" for f in fontes],
            exemplos_treino=len(corpus.treino),
            metricas_teste=avaliar(pipeline, corpus.teste),
        )
        return cls(pipeline, metadados)

    def classificar(self, texto: str, sinais: int = 5) -> Previsao:
        probs = self.pipeline.predict_proba([texto])[0]
        classes = list(self._logistica.classes_)
        ordem = np.argsort(probs)[::-1]
        fluxo = classes[ordem[0]]
        # Contribuição de cada n-grama da mensagem para o fluxo escolhido (peso * tf-idf).
        x = self._tfidf.transform([texto]).toarray()[0]
        # Original (Enzo): contribuicao = x * self._logistica.coef_[ordem[0]]
        # Com só dois fluxos, a regressão tem uma linha de pesos só, a do segundo: a do primeiro é
        # a mesma com o sinal trocado (achado pelo teste de contrato ao incorporar, 01/10).
        pesos = self._logistica.coef_
        if pesos.shape[0] == 1:
            pesos = np.vstack([-pesos[0], pesos[0]])
        contribuicao = x * pesos[ordem[0]]
        principais = [i for i in np.argsort(contribuicao)[::-1][:sinais] if contribuicao[i] > 0]
        return Previsao(
            fluxo=fluxo,
            confianca=round(float(probs[ordem[0]]), 4),
            probabilidades=[
                Probabilidade(fluxo=classes[i], probabilidade=round(float(probs[i]), 4))
                for i in ordem
            ],
            sinais=[self._ngramas[i].replace(" ", "_") for i in principais],
            modelo=self.metadados.versao,
        )

    def fluxos(self, textos: Sequence[str]) -> list[tuple[Fluxo, float]]:
        """Fluxo e confiança de cada texto, em lote (avaliação; a rota usa `classificar`)."""
        probs = self.pipeline.predict_proba(list(textos))
        classes = list(self._logistica.classes_)
        return [(classes[int(np.argmax(p))], float(np.max(p))) for p in probs]

    def salvar(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"pipeline": self.pipeline, "metadados": self.metadados.model_dump()}, caminho)

    @classmethod
    def carregar(cls, caminho: Path) -> "Classificador":
        # Artefato produzido pelo próprio build (joblib/pickle): nunca carregar de origem externa.
        if not caminho.is_file():
            raise ModeloInvalido(f"modelo de intenção ausente em {caminho}")
        conteudo = joblib.load(caminho)
        if not isinstance(conteudo, dict) or set(conteudo) != {"pipeline", "metadados"}:
            raise ModeloInvalido(f"formato inesperado em {caminho}")
        return cls(conteudo["pipeline"], Metadados(**conteudo["metadados"]))
