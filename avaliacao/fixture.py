"""A fixture versionada do commit (`data/fixture/raw`), lida como texto, sem o código do produto.

A camada curada repete as regras publicadas (G3 e G4): vale a versão de `process_date` mais
recente; versões diferentes nessa data são conflito, e valor não numérico é quarentena. As duas
ficam fora.
"""

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path


def tabela(raiz: Path, nome: str) -> list[dict]:
    """As linhas de `nome.csv` ou de todos os CSV da pasta `nome/` (partições), como texto."""
    arquivo = raiz / f"{nome}.csv"
    arquivos = [arquivo] if arquivo.is_file() else sorted((raiz / nome).rglob("*.csv"))
    if not arquivos:
        raise FileNotFoundError(f"sem a tabela {nome} em {raiz}")
    linhas = []
    for caminho in arquivos:
        with caminho.open(encoding="utf-8-sig", newline="") as entrada:
            linhas += list(csv.DictReader(entrada))
    return linhas


def linhas_curadas(raiz: Path) -> dict[str, dict]:
    """{transação: linha} da camada curada, com o valor em `valor` (Decimal)."""
    versoes: dict[str, list[dict]] = {}
    for linha in tabela(raiz, "transactions"):
        versoes.setdefault(linha["transaction_id"], []).append(linha)
    saida = {}
    for transacao, linhas in versoes.items():
        recente = max(linha["process_date"] for linha in linhas)
        ultimas = {
            tuple(sorted(linha.items())): linha
            for linha in linhas
            if linha["process_date"] == recente
        }
        if len(ultimas) != 1:
            continue
        linha = dict(next(iter(ultimas.values())))
        try:
            linha["valor"] = Decimal(linha["amount"])
        except (InvalidOperation, TypeError):
            continue
        saida[transacao] = linha
    return saida


def cartoes(raiz: Path, cliente: str) -> list[dict]:
    """Os cartões do cliente (produto cujo tipo começa com "Tarjeta"): id, tipo, status, número
    inteiro e final de 4 dígitos, quando a base tem o número."""
    saida = []
    for produto in sorted(tabela(raiz, "products"), key=lambda p: p["product_id"]):
        if produto["customer_id"] != cliente or not produto["product_type"].startswith("Tarjeta"):
            continue
        numero = produto.get("product_number") or None
        saida.append(
            {
                "product_id": produto["product_id"],
                "tipo": produto["product_type"],
                "status": produto["product_status"],
                "numero": numero,
                "final": (numero or "")[-4:] or None,
            }
        )
    return saida
