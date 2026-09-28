"""O contrato versionado em contrato/openapi.json é exatamente o que a API publica.

Evita que frontend e backend divirjam: mudar a API sem regenerar o contrato (make contrato) falha.
"""

import json
from pathlib import Path

from jeje.config import Settings
from jeje.contrato import gerar

CONTRATO = Path("/contrato/openapi.json")


def test_contrato_versionado_coincide_com_a_api():
    versionado = json.loads(CONTRATO.read_text(encoding="utf-8"))
    atual = json.loads(gerar(Settings()))
    assert atual == versionado
