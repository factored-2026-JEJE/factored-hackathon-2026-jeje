"""Aplicação HTTP. Rotas de domínio entram por casos de uso, não aqui diretamente."""

from fastapi import FastAPI

from jeje import __version__
from jeje.config import Settings


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="JEJE", version=__version__, root_path=settings.api_root_path)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness do processo; não verifica banco nem provedores de IA."""
        return {"status": "ok", "version": __version__}

    return app
