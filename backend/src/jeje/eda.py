"""EDA reproduzível: indicadores que sustentam a escolha do fluxo (R01), sempre com denominador.

Cada indicador é uma consulta SQL versionada sobre as camadas curada/raw:

- `distribuicao`: linhas (grupo, contagem[, soma]); proporção = contagem ÷ total da consulta e,
  havendo soma (ex.: segundos), proporção da soma ÷ soma total;
- `taxa`: linhas (grupo, contagem, base); proporção = contagem ÷ base do próprio grupo.

A consulta vai junto na resposta, para qualquer número ser refeito. Os números descrevem o gerador
do dataset (ACH-020 a 022), não o efeito do sistema.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import Connection, text


@dataclass(frozen=True)
class Indicador:
    id: str
    pergunta: str
    tipo: Literal["distribuicao", "taxa"]
    consulta: str
    unidade_soma: str | None = None


class Linha(BaseModel):
    grupo: str
    contagem: int
    base: int  # denominador da proporção desta linha
    proporcao: float | None
    soma: float | None
    proporcao_soma: float | None


class Resultado(BaseModel):
    id: str
    pergunta: str
    tipo: Literal["distribuicao", "taxa"]
    consulta: str
    unidade_soma: str | None
    linhas: list[Linha]


def _valido(coluna: str, tipo: str) -> str:
    return f"CASE WHEN pg_input_is_valid({coluna}, '{tipo}') THEN {coluna}::{tipo} END"


INDICADORES: tuple[Indicador, ...] = (
    Indicador(
        id="motivos-de-contato",
        pergunta="Qual motivo concentra os contatos e o tempo de atendimento?",
        tipo="distribuicao",
        consulta=(
            "SELECT coalesce(reason_category, '(vazio)') AS grupo, count(*) AS contagem,"
            f" sum({_valido('duration_seconds', 'double precision')}) AS soma"
            " FROM raw.call_center_interactions GROUP BY 1 ORDER BY 2 DESC, 1"
        ),
        unidade_soma="segundos de atendimento",
    ),
    Indicador(
        id="resolucao-por-motivo",
        pergunta="Em que motivos o primeiro contato já resolve?",
        tipo="taxa",
        consulta=(
            "SELECT coalesce(reason_category, '(vazio)') AS grupo,"
            " count(*) FILTER (WHERE was_resolved = 'True') AS contagem, count(*) AS base"
            " FROM raw.call_center_interactions GROUP BY 1 ORDER BY 1"
        ),
    ),
    Indicador(
        id="status-das-transacoes",
        pergunta="Quantas transações terminam num status que costuma gerar dúvida?",
        tipo="distribuicao",
        consulta=(
            "SELECT transaction_status AS grupo, count(*) AS contagem"
            " FROM curated.transactions GROUP BY 1 ORDER BY 2 DESC, 1"
        ),
    ),
    Indicador(
        id="codigos-nas-recusas",
        pergunta="As recusas trazem código de resposta que permita explicar o motivo?",
        tipo="distribuicao",
        consulta=(
            "SELECT coalesce(response_code, '(sem código)') AS grupo, count(*) AS contagem"
            " FROM curated.transactions WHERE transaction_status = 'Declined'"
            " GROUP BY 1 ORDER BY 2 DESC, 1"
        ),
    ),
    Indicador(
        id="reclamacoes-por-categoria",
        pergunta="Que parte das reclamações é sobre transações?",
        tipo="distribuicao",
        consulta=(
            "SELECT category AS grupo, count(*) AS contagem"
            " FROM curated.complaints GROUP BY 1 ORDER BY 2 DESC, 1"
        ),
    ),
    Indicador(
        id="reclamacoes-de-transacao",
        pergunta="Dentro das reclamações de transação, quais subcategorias aparecem?",
        tipo="distribuicao",
        consulta=(
            "SELECT coalesce(subcategory, '(vazio)') AS grupo, count(*) AS contagem"
            " FROM curated.complaints WHERE category = 'Transactions'"
            " GROUP BY 1 ORDER BY 2 DESC, 1"
        ),
    ),
    Indicador(
        id="idiomas-nas-transcricoes",
        pergunta="Em que idiomas estão as conversas registradas (há português)?",
        tipo="distribuicao",
        consulta=(
            "SELECT coalesce(detected_language, '(vazio)') AS grupo, count(*) AS contagem"
            " FROM raw.call_transcripts GROUP BY 1 ORDER BY 2 DESC, 1"
        ),
    ),
)


def _fracao(numerador: float | None, denominador: float | None) -> float | None:
    return None if numerador is None or not denominador else numerador / denominador


def calcular(conexao: Connection, indicador: Indicador) -> Resultado:
    linhas = conexao.execute(text(indicador.consulta)).mappings().all()
    total = sum(linha["contagem"] for linha in linhas)
    somas = [float(linha["soma"]) if linha.get("soma") is not None else None for linha in linhas]
    total_soma = sum(s for s in somas if s is not None)
    resultado = []
    for linha, soma in zip(linhas, somas, strict=True):
        base = linha["base"] if indicador.tipo == "taxa" else total
        resultado.append(
            Linha(
                grupo=linha["grupo"],
                contagem=linha["contagem"],
                base=base,
                proporcao=_fracao(linha["contagem"], base),
                soma=soma,
                proporcao_soma=_fracao(soma, total_soma),
            )
        )
    return Resultado(
        id=indicador.id,
        pergunta=indicador.pergunta,
        tipo=indicador.tipo,
        consulta=indicador.consulta,
        unidade_soma=indicador.unidade_soma,
        linhas=resultado,
    )
