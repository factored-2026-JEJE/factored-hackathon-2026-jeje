"""Aplicação HTTP. Rotas de domínio entram por casos de uso, não aqui diretamente."""

from fastapi import FastAPI

from jeje import __version__

app = FastAPI(title="JEJE", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness do processo; não verifica banco nem provedores de IA."""
    return {"status": "ok", "version": __version__}
