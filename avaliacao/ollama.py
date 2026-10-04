"""Cliente mínimo da API do Ollama do atacante, só com a biblioteca padrão."""

import json
import urllib.request


class Ollama:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def _pedir(self, caminho: str, corpo: dict | None = None, timeout: float = 300.0) -> dict:
        dados = json.dumps(corpo).encode() if corpo is not None else None
        pedido = urllib.request.Request(
            self.base + caminho, data=dados, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
            return json.loads(resposta.read())

    def versao(self) -> str:
        return self._pedir("/api/version", timeout=10)["version"]

    def carregar(self, modelo: str) -> None:
        """Carrega o modelo antes do primeiro episódio, para a primeira fala não estourar o
        tempo."""
        self._pedir("/api/generate", {"model": modelo, "keep_alive": "10m"})

    def conversar(self, modelo: str, mensagens: list[dict], opcoes: dict) -> str:
        corpo = {
            "model": modelo,
            "stream": False,
            "keep_alive": "10m",
            "messages": mensagens,
            "options": opcoes,
        }
        return self._pedir("/api/chat", corpo)["message"]["content"]
