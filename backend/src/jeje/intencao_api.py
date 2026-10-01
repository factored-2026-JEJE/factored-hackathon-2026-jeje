"""Rotas HTTP do portão de intenção de Enzo: classificar uma mensagem e publicar a linhagem do
modelo. O artefato vem do build (estágio `intencao`) e é carregado na primeira chamada; sem ele, as
rotas respondem 503 e o resto da API segue, como o leitor (o original exigia o artefato para a API
subir)."""

import logging
import threading
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, StringConstraints, field_validator

from jeje.intencao.modelo import Classificador, Metadados, ModeloInvalido, Previsao

log = logging.getLogger(__name__)
router = APIRouter()
_trava = threading.Lock()
INDISPONIVEL = {503: {"description": "Modelo de intenção indisponível (artefato ausente)"}}


def classificador_da_requisicao(request: Request) -> Classificador:
    """Dependência FastAPI: o classificador do artefato do build, carregado uma vez."""
    estado = request.app.state
    with _trava:
        if getattr(estado, "classificador", None) is None:
            try:
                estado.classificador = Classificador.carregar(estado.settings.intencao_modelo)
            except ModeloInvalido as erro:
                log.warning("portao de intencao indisponivel: %s", erro)
                raise HTTPException(503, "Modelo de intenção indisponível") from None
    return estado.classificador


ClassificadorDep = Annotated[Classificador, Depends(classificador_da_requisicao)]


class Mensagem(BaseModel):
    # Uma mensagem de chat. Os limites valem para o texto recebido, como publica o contrato;
    # só depois os espaços das pontas saem, e texto só com espaços não é classificável (422).
    texto: Annotated[str, StringConstraints(min_length=1, max_length=1000)]

    @field_validator("texto")
    @classmethod
    def com_conteudo(cls, texto: str) -> str:
        if not texto.strip():
            raise ValueError("mensagem sem conteúdo além de espaços")
        return texto.strip()


class CorpoInvalido(BaseModel):
    detail: str


# Corpo com bytes que não são UTF-8: o FastAPI responde 400 antes de validar; JSON
# malformado ou campo inválido é 422.
@router.post(
    "/intencao/classificar",
    responses={
        400: {"model": CorpoInvalido, "description": "Corpo não é UTF-8 decodificável"},
        **INDISPONIVEL,
    },
)
def classificar(mensagem: Mensagem, classificador: ClassificadorDep) -> Previsao:
    """Fluxo mais provável, probabilidade de cada fluxo e os n-gramas que decidiram."""
    return classificador.classificar(mensagem.texto)


@router.get("/intencao/modelo", responses=INDISPONIVEL)
def modelo(classificador: ClassificadorDep) -> Metadados:
    """Versão, fontes fixadas e métricas no held-out por idioma do modelo em uso."""
    return classificador.metadados
