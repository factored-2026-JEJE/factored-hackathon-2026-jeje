"""Transações do cliente da sessão. Não há parâmetro que escolha o cliente."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request
from pydantic import BaseModel

from jeje import consultas, politica, pre_caso
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


class DecisaoDaPolitica(BaseModel):
    regra: str
    acao: str
    detalhe: str | None


class Situacao(BaseModel):
    transacao: consultas.Transacao
    decisao: DecisaoDaPolitica


def decisao_para_resposta(decisao: politica.Decisao) -> DecisaoDaPolitica:
    return DecisaoDaPolitica(regra=decisao.regra, acao=decisao.acao, detalhe=decisao.detalhe)


@router.get(
    "/minhas/transacoes/{transaction_id}/situacao", responses={404: {"description": NAO_ENCONTRADA}}
)
def situacao(
    transaction_id: Annotated[str, Path(pattern=ID_DA_BASE)],
    ativa: SessaoDep,
    engine: EngineDep,
    request: Request,
) -> Situacao:
    """Fatos da transação e a decisão da política para uma consulta sobre ela (POL-CON-*)."""
    with engine.connect() as conexao:
        fatos = consultas.fatos_da_transacao(conexao, ativa.customer_id, transaction_id)
        transacao = consultas.transacao_do_cliente(conexao, ativa.customer_id, transaction_id)
    if fatos is None or transacao is None:
        raise HTTPException(status_code=404, detail=NAO_ENCONTRADA)
    limites = request.app.state.settings.limites()
    return Situacao(
        transacao=transacao,
        decisao=decisao_para_resposta(politica.decidir_consulta(fatos, limites)),
    )


@router.get(
    "/minhas/transacoes/{transaction_id}/contestacao",
    responses={404: {"description": NAO_ENCONTRADA}},
)
def avaliar_contestacao(
    transaction_id: Annotated[str, Path(pattern=ID_DA_BASE)],
    ativa: SessaoDep,
    engine: EngineDep,
    request: Request,
) -> DecisaoDaPolitica:
    """Avalia, sem criar nada, se uma contestação desta transação pode virar pré-caso (a mesma
    avaliação da proposta: pré-caso existente, limites e total noturno do dia)."""
    limites = request.app.state.settings.limites()
    with engine.connect() as conexao:
        try:
            _, decisao = pre_caso.avaliar(conexao, ativa.customer_id, transaction_id, limites)
        except pre_caso.NaoEncontrada:
            raise HTTPException(status_code=404, detail=NAO_ENCONTRADA) from None
    return decisao_para_resposta(decisao)
