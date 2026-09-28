"""Acesso ao PostgreSQL: um engine por processo, criado a partir da configuração."""

import logging
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolEsgotado

from jeje.config import Settings

log = logging.getLogger("jeje.db")

# Banco fora, conexão caída, timeout, conflito transitório ou pool esgotado (todas as conexões
# ocupadas além da espera do compose): tentar de novo pode dar certo.
INDISPONIVEL = (OperationalError, InterfaceError, PoolEsgotado)


def create_db_engine(settings: Settings, statement_timeout_ms: int | None = None) -> Engine:
    """Engine com timeout de conexão e pool do compose; `statement_timeout_ms` limita cada comando
    (só a API usa: a carga e os scripts podem levar minutos)."""
    opcoes = {"connect_timeout": settings.db_connect_timeout_s}
    if statement_timeout_ms is not None:
        opcoes["options"] = f"-c statement_timeout={statement_timeout_ms}"
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        # O SQLAlchemy não anexa os valores dos parâmetros (mensagem do cliente, hash de token) à
        # mensagem de erro. O próprio PostgreSQL ainda pode citar um valor: ver jeje.logs.
        hide_parameters=True,
        connect_args=opcoes,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_max_overflow,
        pool_timeout=settings.db_pool_timeout_s,
    )


def engine_da_requisicao(request: Request) -> Engine:
    """Dependência FastAPI: o engine único criado em `create_app`."""
    return request.app.state.engine


EngineDep = Annotated[Engine, Depends(engine_da_requisicao)]


def banco_indisponivel(request: Request, erro: Exception) -> JSONResponse:
    """Handler da app: banco indisponível vira 503 com Retry-After, não 500 com traceback."""
    causa = getattr(erro, "orig", None) or erro
    motivo = next(iter(str(causa).splitlines()), "")[:200]  # erro de conexão, sem dado de cliente
    log.warning("banco indisponivel erro=%s motivo=%r", type(causa).__name__, motivo)
    return JSONResponse(
        {"detail": "Serviço temporariamente indisponível. Tente de novo em instantes."},
        status_code=503,
        headers={"Retry-After": "5"},
    )
