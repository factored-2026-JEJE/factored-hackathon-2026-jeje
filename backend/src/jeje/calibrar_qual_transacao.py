"""Calibração do "qual transação" (DEV-037): os pesos do ranking e o limiar do conjunto conformal.

Sorteia clientes reais da base (só leitura) com compra, pagamento ou saque nos 60 dias anteriores
ao último dia dos dados; a transação-alvo é uma delas, e as candidatas são todas as do cliente. O
alvo é descrito em ES e em PT com as mesmas pistas sorteadas (valor exato ou de cabeça, data exata
ou relativa, comércio), e a descrição passa pelos extratores do próprio produto (`interpretar` e
`comercio_citado`): é a leitura que a conversa vai ter. Os clientes se dividem em treino (40%),
calibração (20%) e teste (40%), pelo hash. O teste mede o ranking com o conjunto contra o filtro
exato de hoje, nos mesmos casos. Grava só agregados: pesos, limiares, contagens e métricas.

    python -m jeje.calibrar_qual_transacao <arquivo.json> [clientes]
"""

import hashlib
import json
import math
import random
import sys
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Connection, text

from jeje import db, politica
from jeje.config import Settings
from jeje.interpretacao import comercio_citado_e_como, interpretar
from jeje.qual_transacao import (
    ATRIBUTOS,
    Calibracao,
    atributos,
    comercio_que_vale,
    elegiveis,
    limiar,
    resolver,
    tem_pista,
    treinar,
)

SEMENTE, ALFA, JANELA_DIAS, CLIENTES = 20261001, 0.05, 60, 6000
DENSO = 10  # teste de estresse do NOV-09: os históricos de 10 clientes juntos
TIPOS_ALVO = ("Purchase", "Payment", "Withdrawal")
DIVISAO = (("treino", 0.4), ("calibracao", 0.6), ("teste", 1.0))  # limites acumulados
MAXIMO_OPCOES = 5  # o filtro de hoje mostra até 5 (conversa.MAXIMO_OPCOES)
IDIOMAS = ("es", "pt")
INICIOS = {
    "es": ("No reconozco el cobro", "¿Qué pasó con la compra", "Quiero revisar el cargo"),
    "pt": ("Não reconheço a cobrança", "O que houve com a compra", "Quero revisar a cobrança"),
}
MESES = {
    "es": ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
           "octubre", "noviembre", "diciembre"),
    "pt": ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
           "outubro", "novembro", "dezembro"),
}  # fmt: skip
RELATIVAS = {"es": ("de ayer", "de la semana pasada"), "pt": ("de ontem", "da semana passada")}


def parte(cliente: str) -> str:
    x = int(hashlib.sha256(f"{SEMENTE}:{cliente}".encode()).hexdigest(), 16) % 10_000 / 10_000
    return next(nome for nome, limite in DIVISAO if x < limite)


def _numero(valor: Decimal) -> str:
    """45.90 → "45,90"; 189900.55 → "189.900,55" (os formatos que a conversa lê, ES e PT)."""
    inteiro, centavos = f"{valor:.2f}".split(".")
    return f"{int(inteiro):,}".replace(",", ".") + "," + centavos


def descrever(alvo: politica.Candidata, idioma: str, hoje: date, sorteio: random.Random) -> str:
    """Uma frase do cliente sobre o alvo, com 1 a 3 pistas sorteadas. O sorteio é o mesmo nas duas
    línguas (quem chama passa um gerador com a mesma semente)."""
    tipos = ["valor", "data"] + (["comercio"] if alvo.merchant_name else [])
    escolhidas = sorteio.sample(tipos, sorteio.randint(1, len(tipos)))
    partes = [sorteio.choice(INICIOS[idioma])]
    for tipo in tipos:  # ordem fixa na frase
        if tipo not in escolhidas:
            continue
        if tipo == "valor":
            sorte, unos = sorteio.random(), "de unos " if idioma == "es" else "de uns "
            if sorte < 0.5:
                partes.append("de " + _numero(alvo.amount))
            elif sorte < 0.8 or alvo.amount < 20:
                partes.append(unos + str(round(alvo.amount)))  # de cabeça, sem os centavos
            else:
                partes.append(unos + str(int(round(alvo.amount, -1))))  # de cabeça, na dezena
        elif tipo == "data":
            dia = alvo.transaction_date.date()
            sorte = sorteio.random()
            if sorte < 0.3:
                partes.append(sorteio.choice(RELATIVAS[idioma]))  # a conversa não lê: sem pista
            elif sorte < 0.65:
                partes.append(("del " if idioma == "es" else "do dia ") + f"{dia:%d/%m}")
            else:
                mes = MESES[idioma][dia.month - 1]
                partes.append(("del " if idioma == "es" else "de ") + f"{dia.day} de {mes}")
        else:
            nome = str(alvo.merchant_name)
            if sorteio.random() < 0.3:
                nome = nome.split()[0]  # só a palavra que distingue ("en Streaming")
            partes.append(("en " if idioma == "es" else "na ") + nome)
    return " ".join(partes)


def carregar(conexao: Connection, clientes: int) -> tuple[date, dict[str, list], dict[str, list]]:
    """(hoje, candidatas por cliente, alvos possíveis por cliente), dos clientes sorteados."""
    hoje = conexao.execute(text("SELECT max(transaction_date)::date FROM curated.transactions"))
    hoje = hoje.scalar_one()
    sorteados = conexao.execute(
        text(
            "SELECT customer_id FROM curated.transactions WHERE transaction_type = ANY(:tipos)"
            " AND amount > 0 AND transaction_date::date >= :inicio GROUP BY customer_id"
            " ORDER BY md5(customer_id || :semente) LIMIT :n"
        ),
        {"tipos": list(TIPOS_ALVO), "inicio": hoje - timedelta(days=JANELA_DIAS),
         "semente": str(SEMENTE), "n": clientes},
    ).scalars().all()  # fmt: skip
    linhas = conexao.execute(
        text(
            "SELECT customer_id, transaction_id, amount, transaction_date, merchant_name,"
            " transaction_type FROM curated.transactions WHERE customer_id = ANY(:clientes)"
            " ORDER BY customer_id, transaction_date DESC, transaction_id"
        ),
        {"clientes": list(sorteados)},
    )
    candidatas: dict[str, list] = {}
    alvos: dict[str, list] = {}
    for cliente, tid, valor, quando, comercio, tipo in linhas:
        c = politica.Candidata(tid, valor, quando, comercio)
        candidatas.setdefault(cliente, []).append(c)
        if tipo in TIPOS_ALVO and valor > 0 and (hoje - quando.date()).days <= JANELA_DIAS:
            alvos.setdefault(cliente, []).append(c)
    return hoje, candidatas, alvos


def _caso(chave: str, idioma: str, alvo, candidatas: list, hoje: date, grupo: str) -> dict | None:
    """O alvo descrito e lido pelos extratores do produto; sem pista lida, nenhum caso (sem pista,
    a conversa não usa o ranking)."""
    frase = descrever(alvo, idioma, hoje, random.Random(f"{SEMENTE}:{chave}:frase"))
    comercios = sorted({c.merchant_name for c in candidatas if c.merchant_name})
    lida = interpretar(frase, idioma, hoje)
    comercio = comercio_que_vale(*comercio_citado_e_como(frase, comercios), lida.valor, candidatas)
    pista = politica.Pista(lida.valor, lida.data, comercio, valor_marcado=lida.valor_marcado)
    if not tem_pista(pista):
        return None
    certa = [c.transaction_id for c in candidatas].index(alvo.transaction_id)
    return {"chave": chave, "idioma": idioma, "grupo": grupo, "pista": pista,
            "candidatas": candidatas, "certa": certa}  # fmt: skip


def casos(hoje: date, candidatas: dict, alvos: dict) -> list[dict]:
    """Um caso por cliente e idioma, com o histórico do próprio cliente; e o teste de estresse do
    NOV-09: os históricos de 10 clientes juntos, um histórico denso, com o alvo de um deles."""
    resultado = []
    clientes = sorted(alvos, key=lambda c: hashlib.sha256(f"{SEMENTE}:{c}".encode()).hexdigest())
    for cliente in clientes:
        alvo = random.Random(f"{SEMENTE}:{cliente}:alvo").choice(alvos[cliente])
        for idioma in IDIOMAS:
            resultado.append(_caso(cliente, idioma, alvo, candidatas[cliente], hoje, "historico"))
    for n in range(len(clientes) // DENSO):
        bloco = clientes[n * DENSO : (n + 1) * DENSO]
        juntas = sorted(
            (c for cliente in bloco for c in candidatas[cliente]),
            key=lambda c: (c.transaction_date, c.transaction_id),
            reverse=True,
        )
        sorteio = random.Random(f"{SEMENTE}:denso:{n}")
        alvo = sorteio.choice(alvos[sorteio.choice(bloco)])
        for idioma in IDIOMAS:
            resultado.append(_caso(bloco[0], idioma, alvo, juntas, hoje, "denso"))
    return [c for c in resultado if c is not None]


def _proporcao(acertos: Sequence[bool]) -> float:
    return round(sum(acertos) / len(acertos), 4) if acertos else 0.0


def _na_conversa(caso: dict, modelo: Calibracao | None, hoje: date) -> politica.Resolucao:
    """O que a conversa faz: o filtro exato primeiro; sem nenhuma e com o modelo, o ranking."""
    candidatas, pista = caso["candidatas"], caso["pista"]
    resolucao = politica.resolver_transacao(candidatas, pista, MAXIMO_OPCOES)
    if resolucao.tipo == "nenhuma" and modelo is not None:
        resolucao = resolver(candidatas, pista, modelo, caso["idioma"], hoje, MAXIMO_OPCOES)
    return resolucao


def _medir(grupo: list[dict], modelo: Calibracao, hoje: date) -> dict:
    """A conversa com o ranking contra o filtro exato sozinho, nos mesmos casos: direto certo e
    errado, a certa entre os botões ou na pergunta pelo campo, e o pedido de dados."""
    medidas: dict = {"casos": len(grupo)}
    for nome, com in (("com_ranking", modelo), ("filtro_exato", None)):
        lista = []
        for c in grupo:
            r = _na_conversa(c, com, hoje)
            lista.append((r, c["candidatas"][c["certa"]].transaction_id))
        medidas[nome] = {
            "direto_certo": _proporcao(
                [r.tipo == "unica" and r.transacoes == (t,) for r, t in lista]
            ),
            "direto_errado": _proporcao(
                [r.tipo == "unica" and r.transacoes != (t,) for r, t in lista]
            ),
            "botoes": _proporcao(
                [r.tipo == "varias" and r.campo is None and t in r.transacoes for r, t in lista]
            ),
            "pergunta": _proporcao([r.campo is not None and t in r.transacoes for r, t in lista]),
            "nenhuma": _proporcao([r.tipo == "nenhuma" for r, _ in lista]),
        }
    return medidas


def calibrar(conexao: Connection, clientes: int = CLIENTES) -> dict:
    hoje, candidatas, alvos = carregar(conexao, clientes)
    lista = casos(hoje, candidatas, alvos)
    x = {id(c): atributos(c["candidatas"], c["pista"], hoje) for c in lista}
    por_parte = {nome: [c for c in lista if parte(c["chave"]) == nome] for nome, _ in DIVISAO}
    pesos = treinar([(x[id(c)], c["certa"]) for c in por_parte["treino"]])
    sem_limiar = Calibracao("", ALFA, tuple(float(w) for w in pesos), {})
    limiares = {}
    for idioma in IDIOMAS:
        # O limiar vale onde o ranking age: nos casos em que o filtro exato não acha nenhuma, com a
        # probabilidade entre as candidatas possíveis. A certa fora delas nunca entra no conjunto.
        escores = []
        for c in por_parte["calibracao"]:
            exato = politica.resolver_transacao(c["candidatas"], c["pista"], MAXIMO_OPCOES)
            if c["idioma"] != idioma or exato.tipo != "nenhuma":
                continue
            aceitas = elegiveis(c["candidatas"], c["pista"])
            p = dict(sem_limiar.ordem(x[id(c)], aceitas)) if aceitas else {}
            escores.append(1 - p[c["certa"]] if c["certa"] in p else math.inf)
        limiares[idioma] = round(min(limiar(escores, ALFA), 1.0), 6)
    modelo = Calibracao("", ALFA, tuple(float(w) for w in pesos), limiares)
    teste = {
        idioma: {
            grupo: _medir(
                [c for c in por_parte["teste"] if (c["idioma"], c["grupo"]) == (idioma, grupo)],
                modelo,
                hoje,
            )
            for grupo in ("historico", "denso")
        }
        for idioma in IDIOMAS
    }
    entrada = {
        "pesos": [round(float(w), 6) for w in pesos],
        "limiares": limiares,
        "parametros": [SEMENTE, ALFA, JANELA_DIAS, clientes, DENSO, ATRIBUTOS],
    }
    versao = hashlib.sha256(json.dumps(entrada, sort_keys=True).encode()).hexdigest()[:12]
    return {
        "versao": versao,
        "alfa": ALFA,
        "pesos": dict(zip(ATRIBUTOS, (round(float(w), 6) for w in pesos), strict=True)),
        "limiares": limiares,
        "casos": {nome: len(grupo) for nome, grupo in por_parte.items()},
        "clientes": len(alvos),
        "teste": teste,
    }


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 2
    engine = db.create_db_engine(Settings())
    with engine.connect() as conexao:
        resultado = calibrar(conexao, int(argv[2]) if len(argv) == 3 else CLIENTES)
    Path(argv[1]).write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(resultado["teste"], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
