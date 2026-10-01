"""Acesso dos jurados (PRD-009): a demonstração com dados reais só abre com a senha.

A senha vem do `.env` de quem publica (nunca do Git) e nunca vai para o log. Quem acerta recebe um
cookie HttpOnly com a validade assinada por HMAC; a chave sai da própria senha, então trocar a senha
invalida todos os cookies. Sem senha configurada, o portão fica desligado: desenvolvimento, CI e as
suítes da validação seguem iguais. O portão fica na API, e não no proxy: o app manda a sessão em
`Authorization: Bearer`, que substituiria a senha de um `basic_auth` do navegador.
"""

import hashlib
import hmac
import time

from fastapi import Request
from fastapi.responses import JSONResponse

COOKIE = "jeje_acesso"
# O que abre sem o cookie: a saúde (healthcheck e monitoração) e o próprio acesso.
LIVRES = frozenset({"/health", "/health/ready", "/acesso"})


def _chave(senha: str) -> bytes:
    return hashlib.sha256(b"jeje-acesso\x00" + senha.encode()).digest()


def confere(enviada: str, senha: str) -> bool:
    """Senha certa? Compara os resumos em tempo constante (mesmo tamanho para qualquer senha)."""
    return hmac.compare_digest(
        hashlib.sha256(enviada.encode()).digest(), hashlib.sha256(senha.encode()).digest()
    )


def emitir(senha: str, agora: float, validade_s: int) -> str:
    """Valor do cookie: a expiração e a assinatura dela, `<expira>.<hmac>`."""
    expira = str(int(agora) + validade_s)
    return f"{expira}.{hmac.new(_chave(senha), expira.encode(), 'sha256').hexdigest()}"


def valido(valor: str | None, senha: str, agora: float) -> bool:
    """Cookie assinado com esta senha e ainda dentro da validade."""
    expira, _, assinatura = (valor or "").partition(".")
    if not expira.isdigit() or int(expira) <= agora:
        return False
    esperada = hmac.new(_chave(senha), expira.encode(), "sha256").hexdigest()
    return hmac.compare_digest(assinatura, esperada)


def liberado(request: Request) -> bool:
    """Sem senha configurada, tudo abre; com ela, só quem tem o cookie válido."""
    senha = request.app.state.settings.acesso_senha.get_secret_value()
    return not senha or valido(request.cookies.get(COOKIE), senha, time.time())


async def portao(request: Request, call_next):
    """Middleware: fora as rotas livres, sem o cookie de acesso a resposta é 401."""
    caminho = request.url.path
    raiz = request.scope.get("root_path", "")
    if raiz and caminho.startswith(raiz):
        caminho = caminho[len(raiz) :]
    if caminho in LIVRES or liberado(request):
        return await call_next(request)
    return JSONResponse({"detail": "acesso_restrito"}, status_code=401)
