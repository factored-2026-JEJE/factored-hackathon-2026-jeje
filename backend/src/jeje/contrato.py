"""Exporta o contrato OpenAPI da API (fonte dos tipos do frontend).

Uso (via compose): python -m jeje.contrato > contrato/openapi.json
"""

import json
import sys

from jeje.api import create_app
from jeje.config import Settings


def gerar(settings: Settings) -> str:
    esquema = create_app(settings).openapi()
    return json.dumps(esquema, ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    sys.stdout.write(gerar(Settings()))
