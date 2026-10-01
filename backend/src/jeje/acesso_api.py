"""Rotas do acesso dos jurados (PRD-009): a situação do portão e a entrada com a senha."""

import logging
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from jeje import acesso
from jeje.sessao_api import CORPO_ILEGIVEL

log = logging.getLogger(__name__)
router = APIRouter()


class SituacaoDoAcesso(BaseModel):
    restrito: bool = Field(description="A demonstração pede a senha dos jurados")
    liberado: bool = Field(description="Quem pergunta já pode usar a demonstração")


class PedidoDeAcesso(BaseModel):
    senha: str = Field(min_length=1, max_length=200)


@router.get("/acesso")
def situacao(request: Request) -> SituacaoDoAcesso:
    restrito = bool(request.app.state.settings.acesso_senha.get_secret_value())
    return SituacaoDoAcesso(restrito=restrito, liberado=acesso.liberado(request))


@router.post(
    "/acesso/entrada",
    status_code=204,
    responses={**CORPO_ILEGIVEL, 401: {"description": "Senha incorreta"}},
)
def entrar(pedido: PedidoDeAcesso, request: Request, response: Response) -> None:
    """Senha certa: cookie HttpOnly com a validade do compose. Sem senha configurada, nada a
    fazer. A senha nunca vai para o log."""
    config = request.app.state.settings
    senha = config.acesso_senha.get_secret_value()
    if not senha:
        return
    if not acesso.confere(pedido.senha, senha):
        log.warning("acesso recusado: senha incorreta")
        raise HTTPException(status_code=401, detail="senha_incorreta")
    validade = config.acesso_validade_horas * 3600
    response.set_cookie(
        acesso.COOKIE,
        acesso.emitir(senha, time.time(), validade),
        max_age=validade,
        path="/",
        httponly=True,
        samesite="strict",
        secure=config.acesso_cookie_seguro,
    )
    log.info("acesso liberado validade_h=%s", config.acesso_validade_horas)
