"""Logs do processo: uma linha por acontecimento, em texto chave=valor, com o id da requisição.

Só entram rota-modelo, status, tempos, regras, ações, classes de erro e identificadores gerados
pelo sistema (conversa, protocolo, atendimento). Nunca a mensagem do cliente, token, identificador
de cliente nem parâmetros de SQL: o trace completo de cada turno fica no banco (`app.eventos`).
Erro inesperado entra com arquivos, linhas e classes, sem as mensagens das exceções: o PostgreSQL
repete valores nelas (ex.: `invalid input syntax for type integer: "<valor>"`).
"""

import logging
import re
import sys
import time
import traceback
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from fastapi import Request, Response
from fastapi.responses import JSONResponse

CABECALHO = "X-Request-ID"
# Id recebido só é reaproveitado se for curto e sem espaço/controle (nada injeta linha no log).
FORMATO_DO_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
# Sondas do healthcheck (a cada poucos segundos) só aparecem em DEBUG, a menos que falhem.
ROTAS_DE_SAUDE = {"/health", "/health/ready"}

id_da_requisicao: ContextVar[str] = ContextVar("id_da_requisicao", default="-")

log = logging.getLogger("jeje.http")


class _ComIdDaRequisicao(logging.Filter):
    def filter(self, registro: logging.LogRecord) -> bool:
        registro.req = id_da_requisicao.get()
        return True


def configurar(nivel: str) -> None:
    """Handler único do logger `jeje` na saída padrão. Idempotente (a app pode ser recriada)."""
    raiz = logging.getLogger("jeje")
    for handler in [h for h in raiz.handlers if getattr(h, "jeje", False)]:
        raiz.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.jeje = True
    handler.addFilter(_ComIdDaRequisicao())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s req=%(req)s %(message)s")
    )
    raiz.addHandler(handler)
    raiz.setLevel(nivel)


def sem_mensagens(erro: BaseException) -> str:
    """Traceback da cadeia de exceções (causa primeiro) só com frames e classes."""
    cadeia: list[BaseException] = []
    atual: BaseException | None = erro
    while atual is not None and atual not in cadeia:
        cadeia.append(atual)
        atual = atual.__cause__ or atual.__context__
    blocos = []
    for excecao in reversed(cadeia):
        quadros = "".join(traceback.format_list(traceback.extract_tb(excecao.__traceback__)))
        classe = type(excecao)
        blocos.append(f"{quadros}{classe.__module__}.{classe.__qualname__}")
    return "\n-- levou a --\n".join(blocos)


def _rota(request: Request) -> str:
    """Rota-modelo (ex.: /conversas/{conversa_id}/turnos): agrega e não grava IDs crus."""
    rota = request.scope.get("route")
    return getattr(rota, "path", "?")


def _nivel(rota: str, status: int) -> int:
    if status >= 500:
        return logging.WARNING
    if rota in ROTAS_DE_SAUDE and status < 400:
        return logging.DEBUG
    return logging.INFO


async def por_requisicao(
    request: Request, proxima: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Middleware HTTP: id da requisição (recebido válido ou novo) no contexto, na resposta e na
    linha de acesso, com rota, status e duração. Erro não tratado vira 500 JSON e um único log
    com traceback e o mesmo id (quem reporta o problema entrega o id do cabeçalho)."""
    recebido = request.headers.get(CABECALHO, "")
    rid = recebido if FORMATO_DO_ID.fullmatch(recebido) else uuid.uuid4().hex
    marca = id_da_requisicao.set(rid)
    inicio = time.perf_counter()
    try:
        try:
            resposta = await proxima(request)
        except Exception as erro:
            log.error(
                "erro inesperado metodo=%s rota=%s\n%s",
                request.method,
                _rota(request),
                sem_mensagens(erro),
            )
            resposta = JSONResponse(
                {"detail": f"Erro interno inesperado ({CABECALHO} {rid})."}, 500
            )
        resposta.headers[CABECALHO] = rid
        rota = _rota(request)
        ms = (time.perf_counter() - inicio) * 1000
        log.log(
            _nivel(rota, resposta.status_code),
            "acesso metodo=%s rota=%s status=%d ms=%.1f",
            request.method,
            rota,
            resposta.status_code,
            ms,
        )
        return resposta
    finally:
        id_da_requisicao.reset(marca)
