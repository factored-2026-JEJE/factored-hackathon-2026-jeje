"""Aplicação HTTP. Rotas de domínio entram por casos de uso, não aqui diretamente."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from jeje import (
    __version__,
    atendimento_api,
    conversa_api,
    health,
    interpretacao_modelo,
    logs,
    metricas_api,
    parametros,
    pre_caso_api,
    qualidade_api,
    recarga,
    reviews_api,
    sessao_api,
    transacoes_api,
)
from jeje.config import Settings
from jeje.db import INDISPONIVEL, banco_indisponivel, create_db_engine

log = logging.getLogger("jeje.api")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    config = app.state.settings
    log.info(
        "api iniciada versao=%s interpretador=%s modo_demo=%s",
        __version__,
        config.interpretador,
        config.modo_demo,
    )
    app.state.carga_do_modelo = interpretacao_modelo.carregar_em_segundo_plano(
        app.state.interpretador, config.ollama_carga_timeout_s
    )
    yield
    # Fecha as conexões do pool ao encerrar o processo (sem conexões órfãs no banco).
    app.state.engine.dispose()
    log.info("api encerrada")


def create_app(settings: Settings) -> FastAPI:
    logs.configurar(settings.log_level)
    app = FastAPI(
        title="JEJE",
        version=__version__,
        root_path=settings.api_root_path,
        lifespan=ciclo_de_vida,
        dependencies=[Depends(parametros.sem_parametro_repetido)],
    )
    app.state.settings = settings
    app.state.engine = create_db_engine(settings, settings.db_statement_timeout_ms)
    # Toda transação da API respeita a recarga dos dados: durante ela, 503 na hora (DEV-020i).
    recarga.proteger(app.state.engine)
    app.state.interpretador = interpretacao_modelo.configurado(settings)
    app.include_router(health.router)
    app.include_router(qualidade_api.router)
    app.include_router(sessao_api.router)
    app.include_router(transacoes_api.router)
    app.include_router(pre_caso_api.router)
    app.include_router(conversa_api.router)
    app.include_router(metricas_api.router)
    app.include_router(atendimento_api.router)
    app.include_router(reviews_api.router)
    for erro in INDISPONIVEL:
        app.add_exception_handler(erro, banco_indisponivel)
    app.add_exception_handler(recarga.Recarregando, recarga.em_recarga)
    app.middleware("http")(logs.por_requisicao)
    return app
