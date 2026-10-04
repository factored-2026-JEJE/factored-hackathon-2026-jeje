"""Métricas do atendimento recomputadas dos eventos (G11): só agregados, sem dado de cliente. E os
últimos turnos, para a Operação do app (só com MODO_DEMO, como o console do atendente)."""

from dataclasses import asdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from jeje import eventos, metricas
from jeje.db import EngineDep
from jeje.sessao_api import RESPOSTAS_DEMO, exige_modo_demo

router = APIRouter()


class Latencia(BaseModel):
    p50: float | None
    p95: float | None
    max: float | None


class UsoDoModelo(BaseModel):
    chamadas: int
    fallbacks: int
    tokens_entrada: int
    tokens_saida: int
    chamadas_sem_contagem_de_tokens: int


class Metricas(BaseModel):
    turnos: int
    erros: int
    taxa_de_erro: float | None
    conversas: int
    conversas_encaminhadas: int
    taxa_de_encaminhamento: float | None
    pre_casos_registrados: int
    latencia_ms: Latencia
    acoes: dict[str, int]
    regras: dict[str, int]
    modelo: UsoDoModelo


@router.get("/metricas")
def calcular_metricas(engine: EngineDep) -> Metricas:
    with engine.connect() as conexao:
        return Metricas(**metricas.calcular(conexao))


class EventoRecente(BaseModel):
    criado_em: datetime
    requisicao: str | None
    regra: str | None
    acao: str | None
    efeito: str | None


@router.get("/metricas/eventos", dependencies=[Depends(exige_modo_demo)], responses=RESPOSTAS_DEMO)
def eventos_recentes(
    engine: EngineDep, limite: Annotated[int, Query(ge=1, le=50)] = 8
) -> list[EventoRecente]:
    with engine.connect() as conexao:
        return [EventoRecente(**asdict(e)) for e in eventos.recentes(conexao, limite)]
