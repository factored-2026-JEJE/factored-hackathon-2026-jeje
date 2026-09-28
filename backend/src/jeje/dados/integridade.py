"""Integridade dos arquivos locais contra o manifesto versionado, antes de qualquer carga.

Reporta todos os problemas de uma vez (arquivo ausente, tamanho, sha256 e cabeçalho diferente das
colunas da camada raw), para que nenhum dado divergente chegue ao banco.
"""

import csv
from pathlib import Path

from jeje.dados.manifesto import Arquivo, sha256_de, tabela_do_caminho
from jeje.dados.raw import COLUNAS


def cabecalho(caminho: Path) -> tuple[str, ...]:
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        return tuple(next(csv.reader(arquivo), ()))


def problemas_do_arquivo(diretorio_raw: Path, esperado: Arquivo) -> list[str]:
    caminho = diretorio_raw / esperado.caminho
    if not caminho.is_file():
        return [f"{esperado.caminho}: ausente"]
    tamanho = caminho.stat().st_size
    if tamanho != esperado.bytes:
        return [f"{esperado.caminho}: tamanho {tamanho} B, manifesto {esperado.bytes} B"]
    if sha256_de(caminho) != esperado.sha256:
        return [f"{esperado.caminho}: sha256 divergente do manifesto"]
    tabela = tabela_do_caminho(esperado.caminho)
    if cabecalho(caminho) != COLUNAS[tabela]:
        return [f"{esperado.caminho}: cabeçalho difere das colunas raw de {tabela}"]
    return []


def verificar(diretorio_raw: Path, manifesto: dict[str, list[Arquivo]]) -> list[str]:
    return [
        problema
        for arquivos in manifesto.values()
        for esperado in arquivos
        for problema in problemas_do_arquivo(diretorio_raw, esperado)
    ]
