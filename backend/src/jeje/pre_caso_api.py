"""Rotas do pré-caso de contestação: proposta, confirmação e acompanhamento (DEV-012)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request, Response
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from jeje import pre_caso
from jeje.db import EngineDep
from jeje.sessao_api import ID_DA_BASE, RESPOSTAS_SESSAO, SessaoDep
from jeje.transacoes_api import NAO_ENCONTRADA, DecisaoDaPolitica, decisao_para_resposta

router = APIRouter(responses=RESPOSTAS_SESSAO)

ID_PROPOSTA = r"^[A-Za-z0-9_-]{1,64}$"


class Proposta(BaseModel):
    id: str
    transaction_id: str
    expira_em: datetime


class AvaliacaoDeContestacao(BaseModel):
    decisao: DecisaoDaPolitica
    proposta: Proposta | None


class PreCaso(BaseModel):
    protocolo: str
    transaction_id: str
    estado: str
    criado_em: datetime


def _settings(request: Request):
    return request.app.state.settings


@router.post(
    "/minhas/transacoes/{transaction_id}/contestacao/proposta",
    responses={201: {"model": AvaliacaoDeContestacao}, 404: {"description": NAO_ENCONTRADA}},
)
def propor(
    transaction_id: Annotated[str, Path(pattern=ID_DA_BASE)],
    ativa: SessaoDep,
    engine: EngineDep,
    request: Request,
    response: Response,
) -> AvaliacaoDeContestacao:
    """Avalia a contestação e, se a política permitir, cria uma proposta a confirmar."""
    config = _settings(request)
    with engine.begin() as conexao:
        try:
            decisao, proposta = pre_caso.propor(
                conexao,
                ativa.customer_id,
                transaction_id,
                config.limites(),
                config.proposta_ttl_minutos,
            )
        except pre_caso.NaoEncontrada:
            raise HTTPException(status_code=404, detail=NAO_ENCONTRADA) from None
    if proposta is not None:
        response.status_code = 201
    return AvaliacaoDeContestacao(
        decisao=decisao_para_resposta(decisao),
        proposta=None if proposta is None else Proposta(**proposta.__dict__),
    )


@router.post(
    "/minhas/propostas/{proposta_id}/confirmacao",
    status_code=201,
    responses={
        200: {"model": PreCaso, "description": "Já confirmado antes: mesmo protocolo"},
        404: {"description": "Proposta não encontrada"},
        409: {"description": "Proposta vencida ou situação da transação mudou"},
        503: {"description": "Pré-caso não registrado; nada foi criado"},
    },
)
def confirmar(
    proposta_id: Annotated[str, Path(pattern=ID_PROPOSTA)],
    ativa: SessaoDep,
    engine: EngineDep,
    request: Request,
    response: Response,
) -> PreCaso:
    """Confirma a proposta: grava o pré-caso sem duplicar e só responde depois de relê-lo."""
    try:
        with engine.begin() as conexao:
            registrado, criado_agora = pre_caso.confirmar(
                conexao, ativa.customer_id, proposta_id, _settings(request).limites()
            )
    except pre_caso.NaoEncontrada:
        raise HTTPException(status_code=404, detail="Proposta não encontrada") from None
    except pre_caso.Conflito as conflito:
        raise HTTPException(status_code=409, detail=str(conflito)) from None
    except (SQLAlchemyError, RuntimeError):
        # Sem sucesso falso: a transação foi desfeita e o cliente pode tentar de novo.
        raise HTTPException(
            status_code=503, detail="Pré-caso não registrado; nada foi criado. Tente de novo."
        ) from None
    if not criado_agora:
        response.status_code = 200
    return PreCaso(**registrado.__dict__)


@router.get("/minhas/pre-casos")
def meus_pre_casos(ativa: SessaoDep, engine: EngineDep) -> list[PreCaso]:
    """Acompanhamento: pré-casos do cliente da sessão, mais recentes primeiro."""
    with engine.connect() as conexao:
        return [
            PreCaso(**p.__dict__) for p in pre_caso.pre_casos_do_cliente(conexao, ativa.customer_id)
        ]
