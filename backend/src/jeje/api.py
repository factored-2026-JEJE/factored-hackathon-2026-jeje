"""Aplicação HTTP. Rotas de domínio entram por casos de uso, não aqui diretamente."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from jeje import __version__, health, pre_caso_api, qualidade_api, sessao_api, transacoes_api
from jeje.config import Settings
from jeje.db import create_db_engine


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    yield
    # Fecha as conexões do pool ao encerrar o processo (sem conexões órfãs no banco).
    app.state.engine.dispose()


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(
        title="JEJE", version=__version__, root_path=settings.api_root_path, lifespan=ciclo_de_vida
    )
    app.state.settings = settings
    app.state.engine = create_db_engine(settings)
    app.include_router(health.router)
    app.include_router(qualidade_api.router)
    app.include_router(sessao_api.router)
    app.include_router(transacoes_api.router)
    app.include_router(pre_caso_api.router)
    return app
