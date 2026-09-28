"""Métricas do atendimento recomputadas dos eventos (G11): só agregados, sem dado de cliente."""

from fastapi import APIRouter
from pydantic import BaseModel

from jeje import metricas
from jeje.db import EngineDep

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
