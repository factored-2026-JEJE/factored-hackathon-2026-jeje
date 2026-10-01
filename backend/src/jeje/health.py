"""Saúde do serviço: liveness (processo vivo) e readiness (pronto para atender clientes)."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError

from jeje import __version__, recarga
from jeje.db import EngineDep
from jeje.models import DatasetVersion

router = APIRouter()


class Liveness(BaseModel):
    status: Literal["ok"]
    version: str


class VersaoRecusada(BaseModel):
    """A versão nova que a carga recusou com esta valendo (ACH-112)."""

    version: str
    motivo: str
    em: datetime


class DatasetInfo(BaseModel):
    version: str
    source: str
    loaded_at: datetime
    recusada: VersaoRecusada | None


class Readiness(BaseModel):
    # ready: banco acessível, migrado e com dataset carregado; só então o serviço atende.
    status: Literal["ready", "unavailable"]
    database: Literal["ok", "unreachable", "not_migrated", "reloading"]
    dataset: DatasetInfo | None


@router.get("/health")
def liveness() -> Liveness:
    """Processo vivo; não consulta dependências."""
    return Liveness(status="ok", version=__version__)


@router.get("/health/ready", responses={503: {"model": Readiness}})
def readiness(response: Response, engine: EngineDep) -> Readiness:
    try:
        with engine.connect() as conexao:
            linha = conexao.execute(
                select(
                    DatasetVersion.version,
                    DatasetVersion.source,
                    DatasetVersion.loaded_at,
                    DatasetVersion.recusada_versao,
                    DatasetVersion.recusada_motivo,
                    DatasetVersion.recusada_em,
                )
            ).first()
    except ProgrammingError:
        response.status_code = 503
        return Readiness(status="unavailable", database="not_migrated", dataset=None)
    except OperationalError:
        response.status_code = 503
        return Readiness(status="unavailable", database="unreachable", dataset=None)
    except recarga.Recarregando:
        response.status_code = 503
        return Readiness(status="unavailable", database="reloading", dataset=None)

    if linha is None:
        response.status_code = 503
        return Readiness(status="unavailable", database="ok", dataset=None)
    recusada = (
        None
        if linha.recusada_versao is None
        else VersaoRecusada(
            version=linha.recusada_versao, motivo=linha.recusada_motivo, em=linha.recusada_em
        )
    )
    dataset = DatasetInfo(
        version=linha.version, source=linha.source, loaded_at=linha.loaded_at, recusada=recusada
    )
    return Readiness(status="ready", database="ok", dataset=dataset)
