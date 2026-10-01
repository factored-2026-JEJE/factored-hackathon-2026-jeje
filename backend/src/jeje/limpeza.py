"""Limpeza dos dados de teste da demonstração (ACH-040), sem recarregar a base.

Apaga o estado do canal: sessões, propostas, pré-casos, bloqueios, encaminhamentos, eventos e as
conversas com os turnos. Ficam a versão dos dados, a raw, a curada, a qualidade e as personas, e
também as reviews do time, com as conversas avaliadas (encerradas): são o retorno de quem testou
(trabalho de Enzo, PRD-009). As sequências não voltam, então PC-, AT- e BL- nunca se repetem. Roda
sob a trava exclusiva da recarga: enquanto limpa, a API responde 503 com Retry-After.

    python -m jeje.limpeza      (make limpar, make demo-limpar)
"""

import logging

from sqlalchemy import Connection, text

from jeje import db, recarga
from jeje.config import Settings

log = logging.getLogger("jeje.limpeza")

# Ordem das chaves estrangeiras: o bloqueio aponta o caso; o turno e a review, a conversa.
APAGADAS = (
    "app.sessoes",
    "app.propostas_pre_caso",
    "app.pre_casos",
    "app.bloqueios",
    "app.handoffs",
    "app.eventos",
)
# O que fica de propósito (o resto do schema app é apagado acima ou filtrado abaixo).
MANTIDAS = ("app.personas", "app.reviews")
AVALIADAS = "SELECT conversa_id FROM app.reviews"


def limpar(conexao: Connection) -> dict[str, int]:
    """Apaga, na transação de quem chama, o estado de teste do canal; devolve quantas linhas saíram
    de cada tabela."""
    recarga.exclusiva(conexao)
    apagadas = {
        tabela: conexao.execute(text(f"DELETE FROM {tabela}")).rowcount for tabela in APAGADAS
    }
    apagadas["app.turnos"] = conexao.execute(
        text(f"DELETE FROM app.turnos WHERE conversa_id NOT IN ({AVALIADAS})")
    ).rowcount
    apagadas["app.conversas"] = conexao.execute(
        text(f"DELETE FROM app.conversas WHERE id NOT IN ({AVALIADAS})")
    ).rowcount
    # As avaliadas ficam como registro da review, sem nada pendente.
    conexao.execute(
        text(
            "UPDATE app.conversas SET estado = 'encerrada', contexto = '{}', atualizada_em = now()"
            " WHERE estado <> 'encerrada'"
        )
    )
    return apagadas


def main() -> None:
    engine = db.create_db_engine(Settings())
    with engine.begin() as conexao:
        apagadas = limpar(conexao)
    for tabela, linhas in apagadas.items():
        log.info("limpeza tabela=%s linhas=%s", tabela, linhas)
        print(f"{tabela}: {linhas} linha(s) apagada(s)")


if __name__ == "__main__":
    main()
