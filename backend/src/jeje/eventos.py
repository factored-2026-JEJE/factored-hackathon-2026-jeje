"""Eventos de atendimento (G11): o trace de cada turno — regra, ação, efeito, fontes, erro e
latência. Nunca carrega token, mensagem do cliente nem texto de erro (só a classe)."""

import json
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class Evento:
    tipo: Literal["turno", "erro"]
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


def desde(inicio: float) -> Decimal:
    """Milissegundos desde `inicio` (time.perf_counter), com três casas."""
    return round(Decimal(time.perf_counter() - inicio) * 1000, 3)


def registrar(conexao: Connection, e: Evento) -> None:
    conexao.execute(
        text(
            "INSERT INTO app.eventos (tipo, conversa_id, numero, intencao, regra, acao, efeito,"
            " fontes, erro, latencia_ms, interpretacao) VALUES (:tipo, :conversa, :numero,"
            " :intencao, :regra, :acao, :efeito, CAST(:fontes AS jsonb), :erro, :latencia,"
            " :interpretacao)"
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
        },
    )
