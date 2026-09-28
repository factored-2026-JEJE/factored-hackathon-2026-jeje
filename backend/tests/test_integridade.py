"""Verificação de integridade: cada divergência entre arquivo e manifesto é reportada."""

from pathlib import Path

import pytest

from jeje.dados import integridade, manifesto
from jeje.dados.raw import COLUNAS

CAMINHO = "complaints/year=2025/month=03/day=10/complaints_20250310.csv"


def csv_da_tabela(tabela: str, linhas: int) -> bytes:
    colunas = COLUNAS[tabela]
    corpo = "".join(",".join(f"v{i}" for _ in colunas) + "\n" for i in range(linhas))
    return ("﻿" + ",".join(colunas) + "\n" + corpo).encode()


@pytest.fixture
def raw_com_manifesto(tmp_path) -> tuple[Path, dict]:
    raiz = tmp_path / "raw"
    destino = raiz / CAMINHO
    destino.parent.mkdir(parents=True)
    destino.write_bytes(csv_da_tabela("complaints", 3))
    (raiz / "branches.csv").write_bytes(csv_da_tabela("branches", 2))
    return raiz, manifesto.gerar(raiz, ["complaints", "branches"])


def test_arquivos_iguais_ao_manifesto_nao_tem_problemas(raw_com_manifesto):
    raiz, esperado = raw_com_manifesto
    assert integridade.verificar(raiz, esperado) == []


def test_conteudo_alterado_com_mesmo_tamanho_e_detectado(raw_com_manifesto):
    raiz, esperado = raw_com_manifesto
    alvo = raiz / CAMINHO
    conteudo = alvo.read_bytes()
    alvo.write_bytes(conteudo.replace(b"v1,", b"v9,", 1))
    assert integridade.verificar(raiz, esperado) == [f"{CAMINHO}: sha256 divergente do manifesto"]


def test_arquivo_truncado_e_detectado_pelo_tamanho(raw_com_manifesto):
    raiz, esperado = raw_com_manifesto
    alvo = raiz / CAMINHO
    alvo.write_bytes(alvo.read_bytes()[:-5])
    [problema] = integridade.verificar(raiz, esperado)
    assert problema.startswith(f"{CAMINHO}: tamanho")


def test_arquivo_ausente_e_todos_os_problemas_sao_listados(raw_com_manifesto):
    raiz, esperado = raw_com_manifesto
    (raiz / CAMINHO).unlink()
    (raiz / "branches.csv").write_bytes(b"x")
    problemas = integridade.verificar(raiz, esperado)
    assert f"{CAMINHO}: ausente" in problemas
    assert any(p.startswith("branches.csv: tamanho") for p in problemas)
    assert len(problemas) == 2


def test_cabecalho_diferente_das_colunas_raw_e_detectado(tmp_path):
    raiz = tmp_path / "raw"
    raiz.mkdir()
    colunas = list(COLUNAS["branches"])
    colunas[0] = "branch_identifier"  # coluna renomeada na fonte
    (raiz / "branches.csv").write_bytes(("﻿" + ",".join(colunas) + "\n").encode())
    esperado = manifesto.gerar(raiz, ["branches"])
    assert integridade.verificar(raiz, esperado) == [
        "branches.csv: cabeçalho difere das colunas raw de branches"
    ]
