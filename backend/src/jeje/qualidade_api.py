"""Rotas HTTP sobre os dados carregados: relatório da curadoria e indicadores da EDA."""

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from jeje import eda
from jeje.dados.contratos import CONTRATOS
from jeje.db import EngineDep

router = APIRouter()


class QualidadeTabela(BaseModel):
    tabela: str
    raw: int
    curado: int
    quarentena: int
    copias_descartadas: int
    # Código da regra (ver jeje.dados.contratos) → quantidade de registros.
    motivos: dict[str, int]
    anulacoes: dict[str, int]
    normalizacoes: dict[str, int]


@router.get("/dados/qualidade")
def relatorio_de_qualidade(engine: EngineDep) -> list[QualidadeTabela]:
    """Relatório da última carga, na ordem de dependência dos contratos."""
    with engine.connect() as conexao:
        linhas = conexao.execute(
            text(
                "select tabela, raw, curado, quarentena, copias_descartadas, motivos, anulacoes,"
                " normalizacoes from quality.relatorio"
                " order by array_position(cast(:ordem as text[]), tabela)"
            ),
            {"ordem": [contrato.tabela for contrato in CONTRATOS]},
        ).all()
    return [QualidadeTabela(**linha._mapping) for linha in linhas]


@router.get("/dados/eda")
def indicadores_da_eda(engine: EngineDep) -> list[eda.Resultado]:
    """Indicadores da EDA calculados na hora sobre a carga atual, cada um com sua consulta."""
    with engine.connect() as conexao:
        return [eda.calcular(conexao, indicador) for indicador in eda.INDICADORES]
