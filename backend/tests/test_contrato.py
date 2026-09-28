"""Contrato HTTP: toda operação publicada no OpenAPI responde conforme o próprio schema.

Schemathesis gera requisições a partir do OpenAPI da aplicação real e verifica status declarados,
tipo de conteúdo, corpo contra o schema e ausência de erro 5xx inesperado.
"""

import pytest
import schemathesis
from conftest import registrar_dataset

from jeje.api import create_app


@pytest.fixture
def esquema_da_api(banco_migrado):
    # Estado normal de operação: banco migrado e um dataset registrado. Os estados 503 da
    # readiness têm testes exatos em test_health.py (Schemathesis trata todo 5xx como falha).
    registrar_dataset(banco_migrado, version="v", source="fixture")
    app = create_app(banco_migrado.model_copy(update={"api_root_path": ""}))
    return schemathesis.openapi.from_asgi("/openapi.json", app)


esquema = schemathesis.pytest.from_fixture("esquema_da_api")


@esquema.parametrize()
def test_api_cumpre_o_proprio_contrato(case):
    case.call_and_validate()
