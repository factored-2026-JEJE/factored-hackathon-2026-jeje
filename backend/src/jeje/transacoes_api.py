"""Transações do cliente da sessão. Não há parâmetro que escolha o cliente."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from jeje import consultas
from jeje.db import EngineDep
from jeje.sessao_api import ID_DA_BASE, RESPOSTAS_SESSAO, SessaoDep

router = APIRouter(responses=RESPOSTAS_SESSAO)

NAO_ENCONTRADA = "Transação não encontrada"


@router.get("/minhas/transacoes")
def minhas_transacoes(
    ativa: SessaoDep, engine: EngineDep, limite: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[consultas.Transacao]:
    with engine.connect() as conexao:
        return consultas.transacoes_do_cliente(conexao, ativa.customer_id, limite)


@router.get("/minhas/transacoes/{transaction_id}", responses={404: {"description": NAO_ENCONTRADA}})
def minha_transacao(
    transaction_id: Annotated[str, Path(pattern=ID_DA_BASE)], ativa: SessaoDep, engine: EngineDep
) -> consultas.Transacao:
    with engine.connect() as conexao:
        transacao = consultas.transacao_do_cliente(conexao, ativa.customer_id, transaction_id)
    if transacao is None:
        # Mesma resposta para inexistente e para transação de outro cliente (R08).
        raise HTTPException(status_code=404, detail=NAO_ENCONTRADA)
    return transacao
