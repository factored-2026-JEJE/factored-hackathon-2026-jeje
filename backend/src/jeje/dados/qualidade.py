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


@dataclass(frozen=True)
class Normalizacao:
    """Regra explícita aplicada ao gravar a curada: `coluna` recebe `valor` quando `quando`."""

    codigo: str
    coluna: str
    quando: str  # condição SQL sobre o registro raw `av`
    valor: str  # expressão SQL sobre `av`


NORMALIZACOES: dict[str, list[Normalizacao]] = {
    # ACH-019: amount_usd vem vazio quando a moeda já é USD; o valor em dólar é o próprio amount.
    "transactions": [
        Normalizacao(
            codigo="N-USD:amount_usd",
            coluna="amount_usd",
            quando="av.currency = 'USD' AND av.amount_usd IS NULL",
            valor="av.amount",
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
    for regra in NORMALIZACOES.get(contrato.tabela, []):
        if regra.coluna == coluna:
            valor = sql.SQL("CASE WHEN {} THEN {} ELSE {} END").format(
                sql.SQL(regra.quando), sql.SQL(regra.valor), valor
            )
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
    # Só chaves repetidas podem ter conflito ou cópia; sem repetição (o caso comum) nada a fazer.
    cursor.execute(
        sql.SQL(
            "CREATE TEMP TABLE repetidas AS SELECT {chave} FROM av WHERE motivos = '{{}}'"
            " GROUP BY {chave} HAVING count(*) > 1"
        ).format(chave=chave)
    )
    if _contar(cursor, sql.SQL("SELECT count(*) FROM repetidas")) == 0:
        cursor.execute("DROP TABLE repetidas")
        return
    conflitantes = sql.SQL(
        "SELECT {chave} FROM av WHERE motivos = '{{}}' AND ({chave}) IN (SELECT * FROM repetidas)"
        " GROUP BY {chave} HAVING count(DISTINCT ROW({dados})) > 1"
    ).format(chave=chave, dados=dados)
    if "process_date" in colunas(contrato):
        _marcar_revisoes(cursor, contrato, conflitantes)
    # Conteúdos diferentes que sobraram (sem data que os ordene) não são escolhidos em silêncio.
    cursor.execute(
        sql.SQL(
            "UPDATE av SET motivos = array_append(motivos, 'Q-PK-CONFLITO')"
            " WHERE motivos = '{{}}' AND ({}) IN ({})"
        ).format(chave, conflitantes)
    )
    repetidas = sql.SQL(
        "SELECT ctid AS id, row_number() OVER (PARTITION BY {chave} ORDER BY _arquivo, _linha) n"
        " FROM av WHERE motivos = '{{}}' AND ({chave}) IN (SELECT * FROM repetidas)"
    ).format(chave=chave)
    cursor.execute(
        sql.SQL("UPDATE av SET copia = true FROM ({}) x WHERE av.ctid = x.id AND x.n > 1").format(
            repetidas
        )
    )
    cursor.execute("DROP TABLE repetidas")


def _marcar_revisoes(cursor: Cursor, contrato: Contrato, conflitantes: sql.Composable) -> None:
    """Revisão (DEV-004): mesma chave publicada de novo num `process_date` posterior substitui a
    anterior. Versões anteriores à mais recente saem da curada como `R-REVISAO-SUBSTITUIDA`
    (auditáveis na quarentena); empate na data mais recente continua conflito."""
    chave = sql.SQL(", ").join(map(sql.Identifier, contrato.chave))
    iguais = sql.SQL(" AND ").join(
        sql.SQL("av.{c} = x.{c}").format(c=sql.Identifier(c)) for c in contrato.chave
    )
    cursor.execute(
        sql.SQL(
            "UPDATE av SET motivos = array_append(motivos, 'R-REVISAO-SUBSTITUIDA')"
            " FROM (SELECT {chave}, max(process_date::date) AS recente FROM av"
            "       WHERE motivos = '{{}}' AND ({chave}) IN ({conflitantes}) GROUP BY {chave}) x"
            " WHERE av.motivos = '{{}}' AND {iguais} AND av.process_date::date < x.recente"
        ).format(chave=chave, conflitantes=conflitantes, iguais=iguais)
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


def _contar_normalizacoes(cursor: Cursor, tabela: str) -> dict[str, int]:
    return {
        regra.codigo: _contar(
            cursor,
            sql.SQL("SELECT count(*) FROM av WHERE {} AND {}").format(
                VALIDOS, sql.SQL(regra.quando)
            ),
        )
        for regra in NORMALIZACOES.get(tabela, [])
    }


def curar_tabela(cursor: Cursor, contrato: Contrato) -> Resumo:
    tabela = contrato.tabela
    _avaliar(cursor, contrato)
    _gravar_quarentena(cursor, tabela)
    anulacoes = _contar_anulacoes(cursor, contrato)
    normalizacoes = _contar_normalizacoes(cursor, tabela)
    _gravar_curado(cursor, contrato)

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


def _chaves_estrangeiras(cursor: Cursor) -> list[tuple[str, str, str]]:
    """(tabela, nome, definição) das FKs da curada, lidas do catálogo (fonte: as migrations)."""
    cursor.execute(
        "SELECT c.conrelid::regclass::text, c.conname, pg_get_constraintdef(c.oid)"
        " FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace"
        " WHERE c.contype = 'f' AND n.nspname = %s ORDER BY c.conname",
        (SCHEMA,),
    )
    return cursor.fetchall()


def curar(cursor: Cursor, tabelas: list[str]) -> dict[str, Resumo]:
    """Refaz a camada curada e a qualidade a partir da raw atual (na transação do chamador).

    As FKs da curada saem durante a gravação e voltam no fim, validadas numa só consulta por
    restrição (em vez de um gatilho por linha): mesma garantia, muito menos tempo. Se algum
    registro violasse uma FK, recriá-la falharia e a transação inteira seria desfeita.
    """
    todas = [sql.Identifier(SCHEMA, c.tabela) for c in CONTRATOS]
    todas += [sql.Identifier(SCHEMA_QUALIDADE, t) for t in ("quarentena", "relatorio")]
    cursor.execute(sql.SQL("TRUNCATE {}").format(sql.SQL(", ").join(todas)))
    chaves = _chaves_estrangeiras(cursor)
    for tabela, nome, _ in chaves:
        cursor.execute(
            sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
                sql.SQL(tabela), sql.Identifier(nome)
            )
        )
    resumos = {
        contrato.tabela: curar_tabela(cursor, contrato)
        for contrato in CONTRATOS
        if contrato.tabela in tabelas
    }
    for tabela, nome, definicao in chaves:
        cursor.execute(
            sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} {}").format(
                sql.SQL(tabela), sql.Identifier(nome), sql.SQL(definicao)
            )
        )
    return resumos
