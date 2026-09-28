"""Rotas da conversa sem modelo (G10): abrir, enviar mensagem (turno) e reabrir o histórico."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from jeje import conversa
from jeje.db import EngineDep
from jeje.pre_caso_api import ID_PROPOSTA, Proposta
from jeje.sessao_api import CORPO_ILEGIVEL, RESPOSTAS_SESSAO, SessaoDep

router = APIRouter(responses=RESPOSTAS_SESSAO)

NAO_ENCONTRADA = "Conversa não encontrada"
ConversaId = Annotated[str, Path(pattern=ID_PROPOSTA)]


class NovaConversa(BaseModel):
    idioma: Literal["es", "pt"]


class ConversaAberta(BaseModel):
    conversa_id: str
    idioma: Literal["es", "pt"]
    estado: str
    resposta: str


class Mensagem(BaseModel):
    texto: str = Field(min_length=1, max_length=conversa.LIMITE_MENSAGEM)


class Opcao(BaseModel):
    numero: int
    transaction_id: str
    descricao: str


class ResultadoDoTurno(BaseModel):
    """O que o turno fez: regra aplicada, efeito verificado e a resposta ao cliente."""

    conversa_id: str
    numero: int
    idioma: Literal["es", "pt"]
    intencao: str
    regra: str
    acao: str
    estado: str
    resposta: str
    transaction_id: str | None
    opcoes: list[Opcao]
    proposta: Proposta | None
    protocolo: str | None
    atendimento: str | None


class TurnoRegistrado(BaseModel):
    numero: int
    mensagem: str
    resposta: str
    regra: str
    acao: str
    estado: str
    criado_em: datetime


class Historico(BaseModel):
    conversa_id: str
    idioma: Literal["es", "pt"]
    estado: str
    turnos: list[TurnoRegistrado]


@router.post("/conversas", status_code=201, responses=CORPO_ILEGIVEL)
def abrir_conversa(pedido: NovaConversa, ativa: SessaoDep, engine: EngineDep) -> ConversaAberta:
    with engine.begin() as conexao:
        conversa_id, saudacao = conversa.abrir(conexao, ativa.customer_id, pedido.idioma)
    return ConversaAberta(
        conversa_id=conversa_id, idioma=pedido.idioma, estado="livre", resposta=saudacao
    )


@router.post(
    "/conversas/{conversa_id}/turnos",
    responses={
        **CORPO_ILEGIVEL,
        404: {"description": NAO_ENCONTRADA},
        503: {"description": "Turno não registrado; nada foi criado"},
    },
)
def enviar_mensagem(
    conversa_id: ConversaId,
    mensagem: Mensagem,
    ativa: SessaoDep,
    engine: EngineDep,
    request: Request,
) -> ResultadoDoTurno:
    """Um turno: a política decide com fatos verificados; efeito só com confirmação explícita."""
    config = request.app.state.settings
    try:
        with engine.begin() as conexao:
            resultado = conversa.turno(
                conexao,
                ativa.customer_id,
                conversa_id,
                mensagem.texto,
                config.limite_pre_caso_usd,
                config.proposta_ttl_minutos,
            )
    except conversa.ConversaNaoEncontrada:
        raise HTTPException(status_code=404, detail=NAO_ENCONTRADA) from None
    except SQLAlchemyError:
        # Sem sucesso falso: o turno inteiro foi desfeito; reenviar a mesma mensagem é seguro.
        raise HTTPException(
            status_code=503, detail="Turno não registrado; nada foi criado. Tente de novo."
        ) from None
    saida = resultado.saida
    return ResultadoDoTurno(
        conversa_id=resultado.conversa_id,
        numero=resultado.numero,
        idioma=resultado.idioma,
        intencao=resultado.intencao,
        regra=saida.regra,
        acao=saida.acao,
        estado=saida.estado,
        resposta=resultado.resposta,
        transaction_id=saida.transaction_id,
        opcoes=[Opcao(**o.__dict__) for o in saida.opcoes],
        proposta=None if saida.proposta is None else Proposta(**saida.proposta.__dict__),
        protocolo=saida.protocolo,
        atendimento=saida.atendimento,
    )


@router.get("/conversas/{conversa_id}", responses={404: {"description": NAO_ENCONTRADA}})
def historico(conversa_id: ConversaId, ativa: SessaoDep, engine: EngineDep) -> Historico:
    """Reabre a conversa (ex.: depois de recarregar a página), só para o dono."""
    with engine.connect() as conexao:
        try:
            dados, turnos = conversa.historico(conexao, ativa.customer_id, conversa_id)
        except conversa.ConversaNaoEncontrada:
            raise HTTPException(status_code=404, detail=NAO_ENCONTRADA) from None
    return Historico(
        conversa_id=dados["id"],
        idioma=dados["idioma"],
        estado=dados["estado"],
        turnos=[TurnoRegistrado(**t) for t in turnos],
    )
