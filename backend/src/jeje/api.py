"""Aplicação HTTP. Rotas de domínio entram por casos de uso, não aqui diretamente."""

from fastapi import FastAPI

from jeje import __version__, health
from jeje.config import Settings
from jeje.db import create_db_engine


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="JEJE", version=__version__, root_path=settings.api_root_path)
    app.state.engine = create_db_engine(settings)
    app.include_router(health.router)
    return app
