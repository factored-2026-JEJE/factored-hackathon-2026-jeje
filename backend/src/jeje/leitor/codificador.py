"""Codificador de frases: multilingual-e5-base (intfloat, MIT), pesos fixados por revisão e sha256.

Transforma cada mensagem num vetor de 768 números (normalizado); o classificador (modelo.py) decide
o fluxo sobre esse vetor. Roda em CPU. O torch e o sentence-transformers só são importados ao
codificar a primeira frase: a imagem de testes não os tem, e os testes usam um codificador falso
com a mesma forma (qualquer chamável `list[str] -> np.ndarray`).
"""

from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

from jeje.leitor.fontes import Arquivo, exigir

NOME = "intfloat/multilingual-e5-base"
REVISAO = "d128750597153bb5987e10b1c3493a34e5a4502a"
_BASE = f"https://huggingface.co/{NOME}/resolve/{REVISAO}"
# O e5 foi treinado com prefixo: "query: " para frases a classificar.
PREFIXO = "query: "

Codificador = Callable[[Sequence[str]], np.ndarray]


def _peso(nome: str, tamanho: int, sha256: str) -> Arquivo:
    return Arquivo(nome, f"{_BASE}/{nome}", tamanho, sha256)


PESOS: tuple[Arquivo, ...] = (
    _peso("config.json", 694, "9dab198f24c8c0879e481cf7822005d5ecbceedbacb390ffafa594e28d31bac4"),
    _peso("model.safetensors", 1112201288,
          "a18a44fad1d0b46ded15928144138cff1135d5cc8233bdd90be5f18822de09a7"),
    _peso("modules.json", 387, "c6e29747481e8b5dd2b58401966aeac910de39092f90cda9a704b1545f902b04"),
    _peso("sentence_bert_config.json", 57,
          "948201d8329907aae938fa62f9ceeed53f5694dacc2b87b9f3b78b37ee986529"),
    _peso("sentencepiece.bpe.model", 5069051,
          "cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865"),
    _peso("special_tokens_map.json", 280,
          "06e405a36dfe4b9604f484f6a1e619af1a7f7d09e34a8555eb0b77b66318067f"),
    _peso("tokenizer_config.json", 418,
          "efb5c0d09722e5fe59a462cd2a9976ee216d55b037597d997cd3fe833216da15"),
    _peso("tokenizer.json", 17082660,
          "62c24cdc13d4c9952d63718d6c9fa4c287974249e16b7ade6d5a85e7bbb75626"),
    _peso("1_Pooling/config.json", 200,
          "f586ab6c734af7b8d14d898bfa7faa886f23b46f86dd1730514309893af13d75"),
)  # fmt: skip


class E5:
    """O e5 carregado de um diretório local com os pesos conferidos (nada é baixado aqui)."""

    def __init__(self, diretorio: Path, lote: int = 64):
        for peso in PESOS:
            exigir(diretorio, peso)
        self.diretorio, self.lote, self._modelo = diretorio, lote, None

    def carregar(self) -> None:
        if self._modelo is None:
            from sentence_transformers import SentenceTransformer

            self._modelo = SentenceTransformer(
                str(self.diretorio), device="cpu", local_files_only=True
            )

    def __call__(self, textos: Sequence[str]) -> np.ndarray:
        self.carregar()
        vetores = self._modelo.encode(
            [PREFIXO + t for t in textos], batch_size=self.lote, normalize_embeddings=True
        )
        return np.asarray(vetores, dtype=np.float32)


class ComMemoria:
    """Cada texto é codificado uma vez só: o treino do leitor e os exemplos do LLM do "não
    entendi" (DEV-042) leem o mesmo corpus, e o e5 é o passo caro do build."""

    def __init__(self, codificar: Codificador):
        self.codificar, self.vistos = codificar, {}

    def __call__(self, textos: Sequence[str]) -> np.ndarray:
        faltam = [t for t in dict.fromkeys(textos) if t not in self.vistos]
        if faltam:
            self.vistos.update(zip(faltam, self.codificar(faltam), strict=True))
        return np.array([self.vistos[t] for t in textos])
