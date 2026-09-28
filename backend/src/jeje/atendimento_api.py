"""Console de atendimento humano simulado (G9/G12): a fila de encaminhamentos abertos.

Só com MODO_DEMO ligado, como o acesso por persona: em produção exigiria autenticação de
operador. Mostra o resumo estruturado (regra, pedido truncado, fatos verificados, ações tentadas e
pendências), nunca a conversa inteira.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from jeje import handoff
from jeje.db import EngineDep
from jeje.sessao_api import RESPOSTAS_DEMO, exige_modo_demo

router = APIRouter()


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
