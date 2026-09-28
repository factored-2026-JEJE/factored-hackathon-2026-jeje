"""Recarga dos dados sem brecha (PRD-002, DEV-020i).

A carga troca a curada inteira numa transação. Uma trava consultiva única separa essa troca do
atendimento: toda transação da API pega a trava compartilhada sem esperar (ocupada → 503 na hora,
com Retry-After), e a carga pega a exclusiva antes de qualquer outra trava. Como a API nunca espera
por ela e a carga a pega primeiro, não há ciclo de espera possível, e nenhuma requisição fica
pendurada durante a recarga.
"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import Connection, Engine, event

# Chave da trava consultiva da recarga: fixa e só desta aplicação ("JEJE" em ASCII).
TRAVA = int.from_bytes(b"JEJE", "big")

log = logging.getLogger("jeje.recarga")


class Recarregando(Exception):
    """A carga está trocando os dados: a transação da API não começa (tente de novo)."""


def proteger(engine: Engine) -> None:
    """Toda transação deste engine (o da API) pega a trava compartilhada da recarga sem esperar."""

    @event.listens_for(engine, "begin")
    def _compartilhada(conexao: Connection) -> None:
        livre = conexao.exec_driver_sql(
            f"SELECT pg_try_advisory_xact_lock_shared({TRAVA})"
        ).scalar_one()
        if not livre:
            raise Recarregando


def em_recarga(request: Request, erro: Exception) -> JSONResponse:
    """Handler da app: 503 com Retry-After enquanto a carga troca os dados (nada foi feito)."""
    log.warning("recarga dos dados em andamento; requisicao recusada")
    return JSONResponse(
        {"detail": "Os dados estão sendo atualizados. Tente de novo em instantes."},
        status_code=503,
        headers={"Retry-After": "30"},
    )
