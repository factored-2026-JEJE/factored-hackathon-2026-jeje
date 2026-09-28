"""Manifesto do dataset: contagem de registros, hashes, persistência e versão.

Hashes e tamanhos esperados foram calculados fora do código testado (`sha256sum`, `wc -c`).
"""

from pathlib import Path

import pytest

from jeje.dados import manifesto
from jeje.dados.manifesto import Arquivo, ManifestoInvalido

# Registro com quebra de linha dentro de campo entre aspas: 2 registros, 4 linhas físicas.
MULTILINHA = b'id,texto\n1,"linha um\nlinha dois"\n2,simples\n'
MULTILINHA_SHA256 = "d02bf4cd8505f651b6e38d0ad827348d2fe3fcdc0064b9c5f349be068be73020"
# Arquivo com BOM UTF-8, como os CSV reais do desafio.
COM_BOM = "﻿id,texto\n1,olá\n".encode()
COM_BOM_SHA256 = "f97a2322b3f0d0303cf9edbe5aad21d583c22e4c4d907b87ad570a099a6b06a6"


def criar(raiz: Path, caminho: str, conteudo: bytes) -> None:
    destino = raiz / caminho
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)


@pytest.fixture
def raw(tmp_path) -> Path:
    raiz = tmp_path / "raw"
    criar(raiz, "transactions/year=2025/month=03/day=10/transactions_20250310.csv", MULTILINHA)
    criar(raiz, "customers.csv", COM_BOM)
    return raiz


def test_gerar_conta_registros_csv_e_nao_linhas(raw):
    gerado = manifesto.gerar(raw, ["transactions"])
    assert gerado["transactions"] == [
        Arquivo(
            caminho="transactions/year=2025/month=03/day=10/transactions_20250310.csv",
            bytes=43,
            sha256=MULTILINHA_SHA256,
            registros=2,
        )
    ]


def test_gerar_trata_bom_e_arquivo_unico(raw):
    gerado = manifesto.gerar(raw, ["customers"])
    assert gerado["customers"] == [
        Arquivo(caminho="customers.csv", bytes=19, sha256=COM_BOM_SHA256, registros=1)
    ]


def test_escrever_e_ler_preservam_o_manifesto(raw, tmp_path):
    gerado = manifesto.gerar(raw, ["customers", "transactions"])
    manifesto.escrever(tmp_path / "manifesto", gerado)
    assert manifesto.ler(tmp_path / "manifesto", ["customers", "transactions"]) == gerado


def test_versao_muda_com_arquivo_e_com_selecao_de_tabelas(raw, tmp_path):
    destino = tmp_path / "manifesto"
    manifesto.escrever(destino, manifesto.gerar(raw, ["customers", "transactions"]))
    v_duas = manifesto.versao(destino, ["customers", "transactions"])
    assert manifesto.versao(destino, ["transactions", "customers"]) == v_duas
    assert manifesto.versao(destino, ["customers"]) != v_duas

    criar(raw, "customers.csv", COM_BOM + b"2,outro\n")
    manifesto.escrever(destino, manifesto.gerar(raw, ["customers", "transactions"]))
    assert manifesto.versao(destino, ["customers", "transactions"]) != v_duas


def test_ler_tabela_sem_manifesto_falha_nomeando_a_tabela(raw, tmp_path):
    manifesto.escrever(tmp_path / "manifesto", manifesto.gerar(raw, ["customers"]))
    with pytest.raises(ManifestoInvalido, match="transactions"):
        manifesto.ler(tmp_path / "manifesto", ["customers", "transactions"])


def test_gerar_tabela_sem_arquivos_falha(raw):
    with pytest.raises(ManifestoInvalido, match="products"):
        manifesto.gerar(raw, ["products"])
