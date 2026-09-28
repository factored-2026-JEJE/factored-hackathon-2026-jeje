"""Rotas de sessão de teste e dependência que identifica o cliente em toda rota protegida."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import text

from jeje import sessao
from jeje.config import Settings
from jeje.db import EngineDep

router = APIRouter()

NAO_AUTENTICADO = {"WWW-Authenticate": "Bearer"}
# Status documentados no OpenAPI de toda rota protegida por sessão.
RESPOSTAS_SESSAO = {401: {"description": "Sessão ausente, inválida ou expirada"}}
RESPOSTAS_DEMO = {404: {"description": "Modo demo desligado ou persona não provisionada"}}

esquema_bearer = HTTPBearer(
    auto_error=False, description="Token da sessão de teste (POST /sessoes)"
)


class Persona(BaseModel):
    customer_id: str
    nome: str


class PedidoDeSessao(BaseModel):
    customer_id: str


class SessaoAberta(BaseModel):
    token: str
    expira_em: datetime
    cliente: Persona


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _exige_modo_demo(request: Request) -> None:
    if not _settings(request).modo_demo:
        raise HTTPException(status_code=404, detail="Not Found")


def sessao_da_requisicao(
    engine: EngineDep,
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(esquema_bearer)],
) -> sessao.SessaoAtiva:
    """Cliente da requisição: só o token de uma sessão válida identifica alguém."""
    if credenciais is None or credenciais.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Sessão ausente", headers=NAO_AUTENTICADO)
    with engine.connect() as conexao:
        ativa = sessao.validar(conexao, credenciais.credentials)
    if ativa is None:
        raise HTTPException(
            status_code=401, detail="Sessão inválida ou expirada", headers=NAO_AUTENTICADO
        )
    return ativa


SessaoDep = Annotated[sessao.SessaoAtiva, Depends(sessao_da_requisicao)]


@router.get("/personas", dependencies=[Depends(_exige_modo_demo)], responses=RESPOSTAS_DEMO)
def listar_personas(engine: EngineDep) -> list[Persona]:
    """Personas de demonstração (acesso de teste explícito, só com MODO_DEMO ligado)."""
    with engine.connect() as conexao:
        linhas = conexao.execute(
            text("SELECT customer_id, nome FROM app.personas ORDER BY ordem")
        ).mappings()
        return [Persona(**linha) for linha in linhas]


@router.post(
    "/sessoes",
    status_code=201,
    dependencies=[Depends(_exige_modo_demo)],
    responses={**RESPOSTAS_DEMO, 400: {"description": "Corpo ilegível (não é JSON UTF-8)"}},
)
def abrir_sessao(pedido: PedidoDeSessao, request: Request, engine: EngineDep) -> SessaoAberta:
    with engine.begin() as conexao:
        try:
            token, expira_em = sessao.abrir(
                conexao, pedido.customer_id, _settings(request).sessao_ttl_minutos
            )
        except sessao.PersonaDesconhecida:
            raise HTTPException(status_code=404, detail="Persona não encontrada") from None
        nome = conexao.execute(
            text("SELECT nome FROM app.personas WHERE customer_id = :c"),
            {"c": pedido.customer_id},
        ).scalar_one()
    return SessaoAberta(
        token=token, expira_em=expira_em, cliente=Persona(customer_id=pedido.customer_id, nome=nome)
    )


@router.get("/sessao", responses=RESPOSTAS_SESSAO)
def sessao_atual(ativa: SessaoDep, engine: EngineDep) -> Persona:
    """Quem está na sessão (o nome vem da persona provisionada)."""
    with engine.connect() as conexao:
        nome = conexao.execute(
            text("SELECT nome FROM app.personas WHERE customer_id = :c"), {"c": ativa.customer_id}
        ).scalar_one_or_none()
    return Persona(customer_id=ativa.customer_id, nome=nome or ativa.customer_id)
