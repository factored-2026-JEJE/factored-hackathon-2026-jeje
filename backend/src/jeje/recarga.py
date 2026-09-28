"""Recarga dos dados sem brecha (PRD-002, DEV-020i).

A carga troca a curada inteira numa transação e, nela mesma, encerra o atendimento em curso: nada
do que foi montado com a versão anterior (foco, opções, proposta, sessão) atravessa a troca. Uma
trava consultiva única separa essa troca do
atendimento: toda transação da API pega a trava compartilhada sem esperar (ocupada → 503 na hora,
com Retry-After), e a carga pega a exclusiva antes de qualquer outra trava. Como a API nunca espera
por ela e a carga a pega primeiro, não há ciclo de espera possível, e nenhuma requisição fica
pendurada durante a recarga.
"""

import logging
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import Connection, Engine, event, text

from jeje.conversa import TERMINAIS

# Chave da trava consultiva da recarga: fixa e só desta aplicação ("JEJE" em ASCII).
TRAVA = int.from_bytes(b"JEJE", "big")
# Quanto a carga espera por qualquer trava (as transações da API em curso terminam em
# milissegundos; esperar mais que isso é uma sessão presa) antes de desistir sem alterar nada.
ESPERA_DA_CARGA_S = 60

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


def exclusiva(conexao: Connection) -> None:
    """Primeiro comando da transação da carga: espera as transações da API em curso terminarem e
    impede que outras comecem até o commit. Nenhuma trava da carga espera mais que o limite."""
    conexao.exec_driver_sql(f"SET LOCAL lock_timeout = '{ESPERA_DA_CARGA_S}s'")
    conexao.exec_driver_sql(f"SELECT pg_advisory_xact_lock({TRAVA})")


@dataclass(frozen=True)
class Encerramento:
    conversas: int
    propostas: int
    sessoes: int


def encerrar_atendimento(conexao: Connection) -> Encerramento:
    """Na transação da carga, depois da troca dos dados: conversas não terminais ficam encerradas
    com o contexto apagado (foco, opções e proposta apontavam para a versão anterior); propostas
    de pré-caso pendentes vencem (confirmar depois dá conflito, nunca pré-caso); todas as sessões
    caem. Conversas com atendente seguem (o contexto só guarda a referência do caso), e
    encaminhamentos e pré-casos ficam como registro: a fotografia dos fatos daquele momento."""
    conversas = conexao.execute(
        text(
            "UPDATE app.conversas SET estado = 'encerrada', contexto = '{}', atualizada_em = now()"
            " WHERE estado <> ALL(:terminais)"
        ),
        {"terminais": sorted(TERMINAIS)},
    ).rowcount
    propostas = conexao.execute(
        text("UPDATE app.propostas_pre_caso SET expira_em = now() WHERE expira_em > now()")
    ).rowcount
    sessoes = conexao.execute(text("DELETE FROM app.sessoes")).rowcount
    return Encerramento(conversas, propostas, sessoes)


def em_recarga(request: Request, erro: Exception) -> JSONResponse:
    """Handler da app: 503 com Retry-After enquanto a carga troca os dados (nada foi feito)."""
    log.warning("recarga dos dados em andamento; requisicao recusada")
    return JSONResponse(
        {"detail": "Os dados estão sendo atualizados. Tente de novo em instantes."},
        status_code=503,
        headers={"Retry-After": "30"},
    )
