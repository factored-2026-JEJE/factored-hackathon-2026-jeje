"""Eventos de atendimento (G11): o trace de cada turno — regra, ação, efeito, fontes, erro e
latência — com o id da requisição que o gerou (o mesmo das linhas do log e do X-Request-ID da
resposta). Nunca carrega token, mensagem do cliente nem texto de erro (só a classe)."""

import json
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import Connection, text

from jeje.logs import id_da_requisicao
from jeje.models import TIPOS_DE_EVENTO


@dataclass(frozen=True)
class Evento:
    tipo: Literal[TIPOS_DE_EVENTO]
    latencia_ms: Decimal
    conversa_id: str | None = None
    numero: int | None = None
    intencao: str | None = None
    regra: str | None = None
    acao: str | None = None
    efeito: str | None = None
    fontes: tuple[str, ...] = ()
    erro: str | None = None
    interpretacao: str | None = None
    modelo_latencia_ms: Decimal | None = None
    modelo_tokens_entrada: int | None = None
    modelo_tokens_saida: int | None = None


def desde(inicio: float) -> Decimal:
    """Milissegundos desde `inicio` (time.perf_counter), com três casas."""
    return round(Decimal(time.perf_counter() - inicio) * 1000, 3)


def registrar(conexao: Connection, e: Evento) -> None:
    # Fora de uma requisição (ex.: a carga dos dados) não há id: fica nulo.
    requisicao = id_da_requisicao.get()
    conexao.execute(
        text(
            "INSERT INTO app.eventos (tipo, conversa_id, numero, intencao, regra, acao, efeito,"
            " fontes, erro, latencia_ms, interpretacao, modelo_latencia_ms, modelo_tokens_entrada,"
            " modelo_tokens_saida, requisicao) VALUES (:tipo, :conversa, :numero, :intencao,"
            " :regra, :acao, :efeito, CAST(:fontes AS jsonb), :erro, :latencia, :interpretacao,"
            " :modelo_ms, :tokens_entrada, :tokens_saida, :requisicao)"
        ),
        {
            "tipo": e.tipo,
            "conversa": e.conversa_id,
            "numero": e.numero,
            "intencao": e.intencao,
            "regra": e.regra,
            "acao": e.acao,
            "efeito": e.efeito,
            "fontes": json.dumps(list(e.fontes)),
            "erro": e.erro,
            "latencia": e.latencia_ms,
            "interpretacao": e.interpretacao,
            "modelo_ms": e.modelo_latencia_ms,
            "tokens_entrada": e.modelo_tokens_entrada,
            "tokens_saida": e.modelo_tokens_saida,
            "requisicao": None if requisicao == "-" else requisicao,
        },
    )


def registrar_acao(
    conexao: Connection,
    inicio: float,
    acao: str,
    efeito: str,
    regra: str | None,
    fontes: tuple[str, ...],
) -> None:
    """Efeito feito fora de um turno (rota direta, atendente): o mesmo trace, na mesma transação
    do efeito, para que a auditoria e as métricas vejam tudo o que foi criado."""
    registrar(
        conexao,
        Evento(
            tipo="acao",
            latencia_ms=desde(inicio),
            acao=acao,
            regra=regra,
            efeito=efeito,
            fontes=fontes,
        ),
    )
