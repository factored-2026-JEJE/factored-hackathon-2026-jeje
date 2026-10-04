"""Cliente HTTP mínimo da API do produto: devolve status e corpo, inclusive em 4xx e 5xx."""

import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request


def alvo_local(url: str) -> bool:
    """Só loopback ou nome de serviço do compose (sem ponto). Assim, a avaliação nunca roda
    contra a publicação (PRD-010, item 3)."""
    host = urllib.parse.urlsplit(url).hostname or ""
    if host == "localhost" or (host and "." not in host and ":" not in host):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def pedir(
    url: str,
    caminho: str,
    token: str | None = None,
    metodo: str = "GET",
    corpo: dict | None = None,
    timeout: float = 30.0,
) -> tuple[int, bytes]:
    """Uma requisição à API, sem seguir nada; com `token`, vai como Bearer."""
    cabecalhos = {"content-type": "application/json"}
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    dados = json.dumps(corpo).encode() if corpo is not None else None
    pedido = urllib.request.Request(url + caminho, method=metodo, headers=cabecalhos, data=dados)
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
            return resposta.status, resposta.read()
    except urllib.error.HTTPError as erro:
        return erro.code, erro.read()


def lista(url: str, caminho: str, token: str | None = None) -> list[dict]:
    """O corpo JSON de uma listagem; vazio quando a API não responde 200."""
    status, corpo = pedir(url, caminho, token)
    return json.loads(corpo) if status == 200 else []
