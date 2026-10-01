"""Console de atendimento humano simulado (G9/G12): a fila de encaminhamentos abertos e os
bloqueios simulados de cartão ativos (PRD-007).

Só com MODO_DEMO ligado, como o acesso por persona: em produção exigiria autenticação de
operador. Mostra o resumo estruturado (regra, pedido truncado, fatos verificados, ações tentadas e
pendências), nunca a conversa inteira.
"""

import logging
import time
from dataclasses import asdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from jeje import bloqueio, eventos, handoff
from jeje.db import EngineDep
from jeje.pre_caso_api import ID_PROPOSTA
from jeje.sessao_api import RESPOSTAS_DEMO, exige_modo_demo

router = APIRouter()
log = logging.getLogger("jeje.atendimento")


class TransacaoResumida(BaseModel):
    transaction_id: str
    data: datetime
    valor: str
    moeda: str
    comercio: str | None
    status: str


class AcaoTentada(BaseModel):
    acao: str
    resultado: str


class Encaminhamento(BaseModel):
    id: str
    customer_id: str
    regra: str
    idioma: str
    pedido: str
    transacao: TransacaoResumida | None
    acoes: list[AcaoTentada]
    pendencias: list[str]
    estado: str
    criado_em: datetime


@router.get("/atendimento/fila", dependencies=[Depends(exige_modo_demo)], responses=RESPOSTAS_DEMO)
def fila(
    engine: EngineDep, limite: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[Encaminhamento]:
    """Encaminhamentos abertos, mais antigos primeiro (ordem de atendimento)."""
    with engine.connect() as conexao:
        return [Encaminhamento(**e) for e in handoff.fila(conexao, limite)]


@router.post(
    "/atendimento/fila/{handoff_id}/assumir",
    dependencies=[Depends(exige_modo_demo)],
    responses={
        404: {"description": "Modo demo desligado ou encaminhamento inexistente"},
        409: {"description": "Encaminhamento já assumido por outro atendente"},
    },
)
def assumir(
    handoff_id: Annotated[str, Path(pattern=ID_PROPOSTA)], engine: EngineDep
) -> Encaminhamento:
    """O atendente assume o caso: ele sai da fila aberta, com o mesmo resumo."""
    inicio = time.perf_counter()
    try:
        with engine.begin() as conexao:
            assumido = Encaminhamento(**handoff.assumir(conexao, handoff_id))
            eventos.registrar_acao(
                conexao,
                inicio,
                "assumir_atendimento",
                assumido.id,
                assumido.regra,
                ("app.handoffs",),
            )
    except handoff.NaoEncontrado:
        raise HTTPException(status_code=404, detail="Encaminhamento não encontrado") from None
    except handoff.JaAssumido:
        raise HTTPException(status_code=409, detail="Encaminhamento já assumido") from None
    log.info("encaminhamento assumido id=%s regra=%s", assumido.id, assumido.regra)
    return assumido


class BloqueioDeCartao(BaseModel):
    """Bloqueio simulado: o cartão aparece só pelo tipo e pelos 4 últimos dígitos."""

    id: str
    customer_id: str
    product_id: str
    produto: str
    ultimos4: str | None
    tipo: str
    motivo: str
    dispositivo: str
    criado_em: datetime
    reversivel_ate: datetime
    desfeito_em: datetime | None
    desfeito_por: str | None
    atendimento: str | None = Field(
        description="Caso do atendente ligado ao bloqueio (AT-…): todo desbloqueio é anotado nele"
    )


@router.get(
    "/atendimento/bloqueios", dependencies=[Depends(exige_modo_demo)], responses=RESPOSTAS_DEMO
)
def bloqueios(
    engine: EngineDep, limite: Annotated[int, Query(ge=1, le=100)] = 20
) -> list[BloqueioDeCartao]:
    """Bloqueios de cartão ativos, os mais recentes primeiro."""
    with engine.connect() as conexao:
        return [BloqueioDeCartao(**asdict(b)) for b in bloqueio.ativos(conexao, limite)]


@router.post(
    "/atendimento/bloqueios/{bloqueio_id}/desbloqueio",
    dependencies=[Depends(exige_modo_demo)],
    responses={
        404: {"description": "Modo demo desligado ou bloqueio inexistente"},
        409: {"description": "Bloqueio já desfeito"},
    },
)
def desbloquear(
    bloqueio_id: Annotated[str, Path(pattern=ID_PROPOSTA)], engine: EngineDep
) -> BloqueioDeCartao:
    """O atendente desfaz o bloqueio a qualquer momento (passado o prazo, só ele desfaz)."""
    inicio = time.perf_counter()
    try:
        with engine.begin() as conexao:
            desfeito = bloqueio.desfazer(conexao, bloqueio_id, "atendente")
            eventos.registrar_acao(
                conexao,
                inicio,
                "desbloquear_cartao",
                desfeito.id,
                "POL-BLQ-05",
                ("app.bloqueios", "app.handoffs") if desfeito.atendimento else ("app.bloqueios",),
            )
    except bloqueio.NaoEncontrado:
        raise HTTPException(status_code=404, detail="Bloqueio não encontrado") from None
    except bloqueio.JaDesfeito:
        raise HTTPException(status_code=409, detail="Bloqueio já desfeito") from None
    log.info("bloqueio desfeito id=%s por=atendente", desfeito.id)
    return BloqueioDeCartao(**asdict(desfeito))
