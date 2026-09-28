"""Curadoria raw → curated com quarentena auditável, em SQL, dentro da transação da carga.

Para cada contrato (em ordem de dependência):

1. avalia cada registro raw e acumula os motivos de quarentena (códigos em `contratos`);
2. chave repetida com conteúdo diferente → `Q-PK-CONFLITO` em todos (nenhuma escolha silenciosa);
   de cópias exatas fica uma só, as demais são contadas como descartadas;
3. grava a quarentena (registro original em JSON, motivos, linhagem);
4. grava a curada tipada, anulando referências acessórias quebradas ou de outro cliente;
5. aplica normalizações explícitas e registra o relatório da tabela.

Invariante: raw = curado + quarentena + cópias descartadas.
"""

import json
from dataclasses import dataclass

from psycopg import Cursor, sql

from jeje.dados.contratos import CONTRATOS, POR_TABELA, Contrato, Referencia, colunas
from jeje.dados.curado import SCHEMA, SCHEMA_QUALIDADE
from jeje.dados.raw import SCHEMA as SCHEMA_RAW

# Normalizações explícitas aplicadas à curada, por tabela: (código, comando).
NORMALIZACOES: dict[str, list[tuple[str, str]]] = {
    # ACH-019: amount_usd vem vazio quando a moeda já é USD; o valor em dólar é o próprio amount.
    "transactions": [
        (
            "N-USD:amount_usd",
            "UPDATE curated.transactions SET amount_usd = amount "
            "WHERE currency = 'USD' AND amount_usd IS NULL",
        )
    ],
}

VALIDOS = sql.SQL("motivos = '{}' AND NOT copia")


@dataclass(frozen=True)
class Resumo:
    raw: int
    curado: int
    quarentena: int
    copias_descartadas: int
    motivos: dict[str, int]
    anulacoes: dict[str, int]
    normalizacoes: dict[str, int]


def _col(coluna: str) -> sql.Composed:
    return sql.SQL("av.{}").format(sql.Identifier(coluna))


def _existe(referencia: Referencia, mesmo_dono: bool) -> sql.Composed:
    """EXISTS do registro referenciado na curada (opcionalmente do mesmo cliente)."""
    alvo = POR_TABELA[referencia.tabela]
    condicao = sql.SQL("x.{} = {}").format(sql.Identifier(alvo.chave[0]), _col(referencia.coluna))
    if mesmo_dono:
        condicao = sql.SQL("{} AND x.customer_id = av.customer_id").format(condicao)
    return sql.SQL("EXISTS (SELECT 1 FROM {} x WHERE {})").format(
        sql.Identifier(SCHEMA, alvo.tabela), condicao
    )


def _inexistente(referencia: Referencia) -> sql.Composed:
    return sql.SQL("{} IS NOT NULL AND NOT {}").format(
        _col(referencia.coluna), _existe(referencia, mesmo_dono=False)
    )


def _de_outro_cliente(referencia: Referencia) -> sql.Composed:
    return sql.SQL("{} AND NOT {}").format(
        _existe(referencia, mesmo_dono=False), _existe(referencia, mesmo_dono=True)
    )


def _caso(condicao: sql.Composable, codigo: str) -> sql.Composed:
    return sql.SQL("CASE WHEN {} THEN {} END").format(condicao, sql.Literal(codigo))


def _motivos(contrato: Contrato) -> sql.Composed:
    """Expressão text[] com os códigos de quarentena de cada registro `av`."""
    casos: list[sql.Composable] = []
    for coluna in colunas(contrato):
        c, tipo = _col(coluna), contrato.tipo(coluna)
        if contrato.obrigatoria(coluna):
            casos.append(_caso(sql.SQL("{} IS NULL").format(c), f"Q-OBRIG:{coluna}"))
        if tipo != "text":
            invalido = sql.SQL("{} IS NOT NULL AND NOT pg_input_is_valid({}, {})").format(
                c, c, sql.Literal(tipo)
            )
            casos.append(_caso(invalido, f"Q-TIPO:{coluna}"))
        if coluna in contrato.dominios:
            fora = sql.SQL("{} IS NOT NULL AND {} <> ALL({})").format(
                c, c, sql.Literal(list(contrato.dominios[coluna]))
            )
            casos.append(_caso(fora, f"Q-DOMINIO:{coluna}"))
    for referencia in contrato.referencias:
        if referencia.essencial:
            casos.append(_caso(_inexistente(referencia), f"Q-REF:{referencia.coluna}"))
            if referencia.mesmo_cliente:
                casos.append(_caso(_de_outro_cliente(referencia), f"Q-PROP:{referencia.coluna}"))
    return sql.SQL("array_remove(ARRAY[{}]::text[], NULL)").format(sql.SQL(", ").join(casos))


def _acessoria(contrato: Contrato, coluna: str) -> Referencia | None:
    return next((r for r in contrato.referencias if r.coluna == coluna and not r.essencial), None)


def _valor_curado(contrato: Contrato, coluna: str) -> sql.Composed:
    valor: sql.Composable = _col(coluna)
    referencia = _acessoria(contrato, coluna)
    if referencia is not None:
        quebrada: sql.Composable = _inexistente(referencia)
        if referencia.mesmo_cliente:
            quebrada = sql.SQL("({}) OR ({})").format(quebrada, _de_outro_cliente(referencia))
        valor = sql.SQL("CASE WHEN {} THEN NULL ELSE {} END").format(quebrada, valor)
    return sql.SQL("{}::{}").format(valor, sql.SQL(contrato.tipo(coluna)))


def _contar(cursor: Cursor, consulta: sql.Composable) -> int:
    cursor.execute(consulta)
    return cursor.fetchone()[0]


def _avaliar(cursor: Cursor, contrato: Contrato) -> None:
    """Tabela temporária `av`: registros raw + motivos + marca de cópia exata."""
    chave = sql.SQL(", ").join(map(sql.Identifier, contrato.chave))
    dados = sql.SQL(", ").join(map(sql.Identifier, colunas(contrato)))
    cursor.execute("DROP TABLE IF EXISTS av")
    # O alias "av" do raw é o mesmo nome usado nas expressões de motivos.
    cursor.execute(
        sql.SQL("CREATE TEMP TABLE av AS SELECT av.*, {}, false AS copia FROM {} av").format(
            sql.SQL("{} AS motivos").format(_motivos(contrato)),
            sql.Identifier(SCHEMA_RAW, contrato.tabela),
        )
    )
    conflitantes = sql.SQL(
        "SELECT {chave} FROM av WHERE motivos = '{{}}' GROUP BY {chave}"
        " HAVING count(DISTINCT ROW({dados})) > 1"
    ).format(chave=chave, dados=dados)
    cursor.execute(
        sql.SQL(
            "UPDATE av SET motivos = array_append(motivos, 'Q-PK-CONFLITO') WHERE ({}) IN ({})"
        ).format(chave, conflitantes)
    )
    repetidas = sql.SQL(
        "SELECT ctid AS id, row_number() OVER (PARTITION BY {} ORDER BY _arquivo, _linha) n"
        " FROM av WHERE motivos = '{{}}'"
    ).format(chave)
    cursor.execute(
        sql.SQL("UPDATE av SET copia = true FROM ({}) x WHERE av.ctid = x.id AND x.n > 1").format(
            repetidas
        )
    )


def _gravar_quarentena(cursor: Cursor, tabela: str) -> None:
    cursor.execute(
        sql.SQL(
            "INSERT INTO {} (tabela, _arquivo, _linha, motivos, registro)"
            " SELECT {}, _arquivo, _linha, motivos,"
            " to_jsonb(av) - 'motivos' - 'copia' - '_arquivo' - '_linha'"
            " FROM av WHERE motivos <> '{{}}'"
        ).format(sql.Identifier(SCHEMA_QUALIDADE, "quarentena"), sql.Literal(tabela))
    )


def _contar_anulacoes(cursor: Cursor, contrato: Contrato) -> dict[str, int]:
    anulacoes: dict[str, int] = {}
    for referencia in contrato.referencias:
        if referencia.essencial:
            continue
        condicoes = {f"A-REF:{referencia.coluna}": _inexistente(referencia)}
        if referencia.mesmo_cliente:
            condicoes[f"A-PROP:{referencia.coluna}"] = _de_outro_cliente(referencia)
        for codigo, condicao in condicoes.items():
            anulacoes[codigo] = _contar(
                cursor,
                sql.SQL("SELECT count(*) FROM av WHERE {} AND {}").format(VALIDOS, condicao),
            )
    return anulacoes


def _gravar_curado(cursor: Cursor, contrato: Contrato) -> None:
    cursor.execute(
        sql.SQL(
            "INSERT INTO {} ({}, _arquivo, _linha) SELECT {}, _arquivo, _linha FROM av WHERE {}"
        ).format(
            sql.Identifier(SCHEMA, contrato.tabela),
            sql.SQL(", ").join(map(sql.Identifier, colunas(contrato))),
            sql.SQL(", ").join(_valor_curado(contrato, c) for c in colunas(contrato)),
            VALIDOS,
        )
    )


def _normalizar(cursor: Cursor, tabela: str) -> dict[str, int]:
    normalizacoes: dict[str, int] = {}
    for codigo, comando in NORMALIZACOES.get(tabela, []):
        cursor.execute(comando)
        normalizacoes[codigo] = cursor.rowcount
    return normalizacoes


def curar_tabela(cursor: Cursor, contrato: Contrato) -> Resumo:
    tabela = contrato.tabela
    _avaliar(cursor, contrato)
    _gravar_quarentena(cursor, tabela)
    anulacoes = _contar_anulacoes(cursor, contrato)
    _gravar_curado(cursor, contrato)
    normalizacoes = _normalizar(cursor, tabela)

    cursor.execute("SELECT m, count(*) FROM av, unnest(motivos) m GROUP BY m ORDER BY m")
    motivos = dict(cursor.fetchall())
    resumo = Resumo(
        raw=_contar(cursor, sql.SQL("SELECT count(*) FROM av")),
        curado=_contar(
            cursor, sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(SCHEMA, tabela))
        ),
        quarentena=_contar(cursor, sql.SQL("SELECT count(*) FROM av WHERE motivos <> '{}'")),
        copias_descartadas=_contar(cursor, sql.SQL("SELECT count(*) FROM av WHERE copia")),
        motivos=motivos,
        anulacoes=anulacoes,
        normalizacoes=normalizacoes,
    )
    cursor.execute(
        sql.SQL(
            "INSERT INTO {} (tabela, raw, curado, quarentena, copias_descartadas, motivos,"
            " anulacoes, normalizacoes) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        ).format(sql.Identifier(SCHEMA_QUALIDADE, "relatorio")),
        (
            tabela,
            resumo.raw,
            resumo.curado,
            resumo.quarentena,
            resumo.copias_descartadas,
            json.dumps(resumo.motivos),
            json.dumps(resumo.anulacoes),
            json.dumps(resumo.normalizacoes),
        ),
    )
    cursor.execute("DROP TABLE av")
    return resumo


def curar(cursor: Cursor, tabelas: list[str]) -> dict[str, Resumo]:
    """Refaz a camada curada e a qualidade a partir da raw atual (na transação do chamador)."""
    todas = [sql.Identifier(SCHEMA, c.tabela) for c in CONTRATOS]
    todas += [sql.Identifier(SCHEMA_QUALIDADE, t) for t in ("quarentena", "relatorio")]
    cursor.execute(sql.SQL("TRUNCATE {}").format(sql.SQL(", ").join(todas)))
    return {
        contrato.tabela: curar_tabela(cursor, contrato)
        for contrato in CONTRATOS
        if contrato.tabela in tabelas
    }
