"""Contrato HTTP: toda operação publicada no OpenAPI responde conforme o próprio schema.

Schemathesis gera requisições a partir do OpenAPI da aplicação real, servida por uvicorn numa
porta local, e verifica status declarados, tipo de conteúdo, corpo contra o schema e ausência de
erro 5xx inesperado.
"""

import pytest
import schemathesis
from conftest import registrar_dataset, servidor_http


@pytest.fixture
def esquema_da_api(banco_migrado):
    # Estado normal de operação: banco migrado e um dataset registrado. Os estados 503 da
    # readiness têm testes exatos em test_health.py (Schemathesis trata todo 5xx como falha).
    registrar_dataset(banco_migrado, version="v", source="fixture")
    with servidor_http(banco_migrado) as url:
        yield schemathesis.openapi.from_url(f"{url}/openapi.json")


esquema = schemathesis.pytest.from_fixture("esquema_da_api")


@esquema.parametrize()
def test_api_cumpre_o_proprio_contrato(case):
    case.call_and_validate()
