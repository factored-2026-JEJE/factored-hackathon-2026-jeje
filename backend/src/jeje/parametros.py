"""Parâmetros de consulta validados na borda (ACH-027).

Com um parâmetro escalar repetido (`?limite=abc&limite=3`), o FastAPI valida só o último valor e
o primeiro passa sem ser visto. Toda rota recusa com 422 um parâmetro de consulta declarado que
chegue repetido; parâmetro não declarado continua ignorado.
"""

from fastapi import Request
from fastapi.dependencies.models import Dependant
from fastapi.exceptions import RequestValidationError


def _declarados(dependente: Dependant) -> set[str]:
    nomes = {p.alias for p in dependente.query_params}
    for sub in dependente.dependencies:
        nomes |= _declarados(sub)
    return nomes


def sem_parametro_repetido(request: Request) -> None:
    rota = request.scope.get("route")
    dependente = getattr(rota, "dependant", None)
    if dependente is None:
        return
    repetidos = sorted(
        nome for nome in _declarados(dependente) if len(request.query_params.getlist(nome)) > 1
    )
    if repetidos:
        raise RequestValidationError(
            [
                {
                    "type": "parametro_repetido",
                    "loc": ("query", nome),
                    "msg": "Parâmetro repetido: envie um valor só",
                    "input": request.query_params.getlist(nome),
                }
                for nome in repetidos
            ]
        )
