"""Tabelas da camada curada (tipadas, com chaves e referências) e do schema de qualidade.

Geradas dos contratos: tipos, NOT NULL, PK e FKs vêm de `contratos.CONTRATOS`. Referência que
exige o mesmo cliente vira FK composta (coluna, customer_id) → (chave, customer_id), então o
próprio banco recusa ligar um registro ao produto de outro cliente.
"""

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Double,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Table,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from jeje.dados.contratos import CONTRATOS, POR_TABELA, Contrato, colunas
from jeje.models import Base

SCHEMA = "curated"
SCHEMA_QUALIDADE = "quality"

TIPO_SQLALCHEMY = {
    "text": Text,
    "integer": Integer,
    "numeric(18,2)": lambda: Numeric(18, 2),
    "double precision": Double,
    "date": Date,
    "timestamp": DateTime,
    "time": Time,
    "boolean": Boolean,
}

# Tabelas referenciadas com exigência de mesmo cliente precisam de UNIQUE (chave, customer_id).
REFERENCIADAS_POR_CLIENTE = {
    referencia.tabela for c in CONTRATOS for referencia in c.referencias if referencia.mesmo_cliente
}


def _coluna(contrato: Contrato, coluna: str) -> Column:
    tipo = TIPO_SQLALCHEMY[contrato.tipo(coluna)]()
    return Column(coluna, tipo, nullable=not contrato.obrigatoria(coluna))


def _tabela(contrato: Contrato) -> Table:
    nome = contrato.tabela
    restricoes = [PrimaryKeyConstraint(*contrato.chave, name=f"pk_{nome}")]
    if nome in REFERENCIADAS_POR_CLIENTE:
        restricoes.append(UniqueConstraint(*contrato.chave, "customer_id", name=f"uq_{nome}_dono"))
    for referencia in contrato.referencias:
        alvo = POR_TABELA[referencia.tabela]
        destino = f"{SCHEMA}.{alvo.tabela}"
        if referencia.mesmo_cliente:
            restricoes.append(
                ForeignKeyConstraint(
                    [referencia.coluna, "customer_id"],
                    [f"{destino}.{alvo.chave[0]}", f"{destino}.customer_id"],
                    name=f"fk_{nome}_{referencia.coluna}_dono",
                )
            )
        else:
            restricoes.append(
                ForeignKeyConstraint(
                    [referencia.coluna],
                    [f"{destino}.{alvo.chave[0]}"],
                    name=f"fk_{nome}_{referencia.coluna}",
                )
            )
    return Table(
        nome,
        Base.metadata,
        *(_coluna(contrato, coluna) for coluna in colunas(contrato)),
        Column("_arquivo", Text, nullable=False),
        Column("_linha", Integer, nullable=False),
        *restricoes,
        schema=SCHEMA,
    )


TABELAS: dict[str, Table] = {contrato.tabela: _tabela(contrato) for contrato in CONTRATOS}

QUARENTENA = Table(
    "quarentena",
    Base.metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("tabela", Text, nullable=False),
    Column("_arquivo", Text, nullable=False),
    Column("_linha", Integer, nullable=False),
    Column("motivos", ARRAY(Text), nullable=False),
    Column("registro", JSONB, nullable=False),
    schema=SCHEMA_QUALIDADE,
)

RELATORIO = Table(
    "relatorio",
    Base.metadata,
    Column("tabela", Text, primary_key=True),
    Column("raw", BigInteger, nullable=False),
    Column("curado", BigInteger, nullable=False),
    Column("quarentena", BigInteger, nullable=False),
    Column("copias_descartadas", BigInteger, nullable=False),
    Column("motivos", JSONB, nullable=False),
    Column("anulacoes", JSONB, nullable=False),
    Column("normalizacoes", JSONB, nullable=False),
    schema=SCHEMA_QUALIDADE,
)
