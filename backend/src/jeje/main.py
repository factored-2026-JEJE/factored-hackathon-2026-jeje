"""Ponto de entrada do servidor: `uvicorn jeje.main:app`. Lê a configuração do ambiente."""

from jeje.api import create_app
from jeje.config import Settings

app = create_app(Settings())
