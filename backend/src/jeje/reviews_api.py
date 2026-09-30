"""Rotas das reviews de teste: quem pode avaliar e a avaliação de uma conversa (só MODO_DEMO)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from jeje import reviews
from jeje.config import ConfigDep
from jeje.conversa import ConversaNaoEncontrada
from jeje.conversa_api import NAO_ENCONTRADA, ConversaId
from jeje.db import EngineDep
from jeje.sessao_api import (
    CORPO_ILEGIVEL,
    RESPOSTAS_DEMO,
    RESPOSTAS_SESSAO,
    SessaoDep,
    exige_modo_demo,
)

router = APIRouter(dependencies=[Depends(exige_modo_demo)], responses=RESPOSTAS_DEMO)

LIMITE_COMENTARIO = 2000


class PedidoDeReview(BaseModel):
    avaliador: str
    nota: int = Field(ge=1, le=5)
    resolveu: Literal["sim", "parcial", "nao"]
    comentario: str = Field(max_length=LIMITE_COMENTARIO)


class ReviewRegistrada(BaseModel):
    review_id: int
    issue_url: str | None


@router.get("/testadores")
def listar_testadores(config: ConfigDep) -> list[str]:
    """Quem do time pode avaliar conversas (logins do GitHub)."""
    return reviews.testadores(config.testadores)


@router.post(
    "/conversas/{conversa_id}/reviews",
    status_code=201,
    responses={**RESPOSTAS_SESSAO, **CORPO_ILEGIVEL, 404: {"description": NAO_ENCONTRADA}},
)
def avaliar_conversa(
    conversa_id: ConversaId,
    pedido: PedidoDeReview,
    ativa: SessaoDep,
    config: ConfigDep,
    engine: EngineDep,
) -> ReviewRegistrada:
    """Grava a review da conversa (só do dono) e, com repositório e token, abre a Issue."""
    if pedido.avaliador not in reviews.testadores(config.testadores):
        raise HTTPException(status_code=422, detail="Avaliador não é do time de teste")
    review = reviews.Review(**pedido.model_dump())
    with engine.begin() as conexao:
        try:
            gravada = reviews.gravar(conexao, ativa.customer_id, conversa_id, review)
        except ConversaNaoEncontrada:
            raise HTTPException(status_code=404, detail=NAO_ENCONTRADA) from None
    issue_url = None
    if config.reviews_repo and config.github_token:
        issue_url = reviews.publicar(
            config.github_api_url,
            config.reviews_repo,
            config.github_token,
            reviews.titulo(review, gravada["turnos"]),
            reviews.corpo(review, ativa.customer_id, gravada["conversa"], gravada["turnos"]),
        )
        if issue_url is not None:
            with engine.begin() as conexao:
                reviews.anotar_issue(conexao, gravada["review_id"], issue_url)
    return ReviewRegistrada(review_id=gravada["review_id"], issue_url=issue_url)
