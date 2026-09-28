"""Carga atômica do dataset na camada raw, com linhagem e versão.

Uma única transação trunca todas as tabelas raw, copia (COPY) cada arquivo do manifesto das
tabelas selecionadas, confere a contagem de registros de cada arquivo e grava
`meta.dataset_version`. Qualquer falha desfaz tudo: o banco continua inteiro na versão anterior,
nunca misturado. Se a versão do manifesto já está no banco, nada é feito.
"""

import csv
import time
from dataclasses import dataclass, field
from pathlib import Path

from psycopg import Cursor, sql
from sqlalchemy import Connection, text

from jeje.config import Settings
from jeje.dados import integridade, manifesto
from jeje.dados.raw import COLUNAS, LINHAGEM, SCHEMA
from jeje.db import create_db_engine


class CargaInvalida(Exception):
    """Arquivos ou contagens divergentes do manifesto; nada foi gravado."""


@dataclass(frozen=True)
class ResultadoCarga:
    versao: str
    carregou: bool  # False quando esta versão já estava no banco
    registros: dict[str, int] = field(default_factory=dict)


def versao_carregada(conexao: Connection) -> str | None:
    return conexao.execute(text("select version from meta.dataset_version")).scalar_one_or_none()


def copiar_arquivo(cursor: Cursor, tabela: str, caminho: Path, relativo: str) -> int:
    """COPY de um CSV para raw.<tabela>; vazio vira NULL; devolve o número de registros."""
    colunas = COLUNAS[tabela]
    comando = sql.SQL("COPY {}.{} ({}) FROM STDIN").format(
        sql.Identifier(SCHEMA),
        sql.Identifier(tabela),
        sql.SQL(", ").join(map(sql.Identifier, (*colunas, *LINHAGEM))),
    )
    registros = 0
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo, cursor.copy(comando) as copia:
        leitor = csv.reader(arquivo)
        next(leitor)  # cabeçalho já conferido pela verificação de integridade
        for registros, valores in enumerate(leitor, start=1):
            if len(valores) != len(colunas):
                raise CargaInvalida(
                    f"{relativo}: registro {registros} com {len(valores)} campos, "
                    f"esperado {len(colunas)}"
                )
            copia.write_row(
                [valor if valor != "" else None for valor in valores] + [relativo, registros]
            )
    return registros


def carregar(
    settings: Settings,
    diretorio_raw: Path,
    diretorio_manifesto: Path,
    tabelas: list[str],
    origem: str,
) -> ResultadoCarga:
    esperado = manifesto.ler(diretorio_manifesto, tabelas)
    versao = manifesto.versao(diretorio_manifesto, tabelas)
    engine = create_db_engine(settings)
    try:
        with engine.connect() as conexao:
            if versao_carregada(conexao) == versao:
                return ResultadoCarga(versao=versao, carregou=False)

        problemas = integridade.verificar(diretorio_raw, esperado)
        if problemas:
            raise CargaInvalida("arquivos divergentes do manifesto:\n" + "\n".join(problemas))

        registros: dict[str, int] = {}
        with engine.begin() as conexao:
            cursor = conexao.connection.driver_connection.cursor()
            todas = sql.SQL(", ").join(sql.Identifier(SCHEMA, tabela) for tabela in COLUNAS)
            cursor.execute(sql.SQL("TRUNCATE {}").format(todas))
            for tabela, arquivos in esperado.items():
                inicio = time.monotonic()
                for arquivo in arquivos:
                    lidos = copiar_arquivo(
                        cursor, tabela, diretorio_raw / arquivo.caminho, arquivo.caminho
                    )
                    if lidos != arquivo.registros:
                        raise CargaInvalida(
                            f"{arquivo.caminho}: {lidos} registros, manifesto {arquivo.registros}"
                        )
                registros[tabela] = sum(a.registros for a in arquivos)
                print(f"[carga] {tabela}: {registros[tabela]} registros em "
                      f"{time.monotonic() - inicio:.1f}s", flush=True)  # fmt: skip
            conexao.execute(
                text(
                    "insert into meta.dataset_version (id, version, source, loaded_at) "
                    "values (1, :versao, :origem, now()) on conflict (id) do update set "
                    "version = excluded.version, source = excluded.source, loaded_at = now()"
                ),
                {"versao": versao, "origem": origem},
            )
        return ResultadoCarga(versao=versao, carregou=True, registros=registros)
    finally:
        engine.dispose()
