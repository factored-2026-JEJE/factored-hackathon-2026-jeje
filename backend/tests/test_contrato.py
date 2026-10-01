"""Contrato HTTP: toda operação publicada no OpenAPI responde conforme o próprio schema.

Schemathesis gera requisições a partir do OpenAPI da aplicação real, servida por uvicorn numa
porta local, e verifica status declarados, tipo de conteúdo, corpo contra o schema e ausência de
erro 5xx inesperado.

No gate, a geração é determinística (mesma semente a cada execução, sem banco de exemplos): um
verde vale igual em qualquer clone (ACH-027). A exploração aleatória fica à parte, fora do gate
(`make contrato-explorar`), e o que ela achar vira teste de regressão explícito, como o
`test_parametros.py`.
"""

import pytest
import schemathesis
from conftest import registrar_dataset, servidor_http
from hypothesis import settings

from jeje.intencao.modelo import Classificador
from jeje.leitor.corpus import Corpus, Exemplo
from jeje.leitor.fontes import Arquivo

DETERMINISTICO = settings(derandomize=True, database=None)


@pytest.fixture
def esquema_da_api(banco_migrado, tmp_path):
    # Estado normal de operação: banco migrado, um dataset registrado e o artefato do portão de
    # intenção (um pequeno, treinado aqui: a imagem de teste não tem o do build). Os estados 503
    # da readiness e do portão têm testes exatos (Schemathesis trata todo 5xx como falha).
    registrar_dataset(banco_migrado, version="v", source="fixture")
    exemplos = [
        Exemplo(texto, fluxo, "es")
        for fluxo, textos in {
            "explicar_recusa": ["pago rechazado", "tarjeta rechazada", "compra rechazada"],
            "relato_de_fraude": ["me robaron la tarjeta", "robaron mi celular", "fraude"],
        }.items()
        for texto in textos
    ]
    Classificador.treinado(
        Corpus(treino=exemplos, calibracao=[], teste=exemplos),
        fontes=(Arquivo("teste.csv", "file:///teste.csv", 1, "a" * 64),),
    ).salvar(tmp_path / "intencao.joblib")
    com_portao = banco_migrado.model_copy(update={"intencao_modelo": tmp_path / "intencao.joblib"})
    with servidor_http(com_portao) as url:
        yield schemathesis.openapi.from_url(f"{url}/openapi.json")


esquema = schemathesis.pytest.from_fixture("esquema_da_api")


@esquema.parametrize()
@DETERMINISTICO
def test_api_cumpre_o_proprio_contrato(case):
    case.call_and_validate()


def test_contrato_do_gate_e_deterministico():
    assert (DETERMINISTICO.derandomize, DETERMINISTICO.database) == (True, None)


@pytest.mark.exploracao
@esquema.parametrize()
@settings(max_examples=300, database=None)
def test_exploracao_aleatoria_do_contrato(case):
    case.call_and_validate()
