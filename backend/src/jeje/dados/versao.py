"""Versão do pipeline de dados: sha256 do código-fonte de `jeje.dados`.

Qualquer mudança em colunas, contratos, curadoria ou carga muda esta versão e obriga a recarga,
mesmo com os mesmos arquivos de dados (camada curada nunca fica defasada do código).
"""

import hashlib
from pathlib import Path

PACOTE = Path(__file__).resolve().parent


def versao_pipeline(pacote: Path = PACOTE) -> str:
    resumo = hashlib.sha256()
    for arquivo in sorted(pacote.glob("*.py")):
        resumo.update(arquivo.name.encode() + b"\0" + arquivo.read_bytes())
    return resumo.hexdigest()
