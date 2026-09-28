"""Carga atômica na camada raw contra o PostgreSQL real.

Os valores esperados vêm dos registros escritos pelo próprio teste (fixture), não do carregador.
"""

import csv
import io
import re
from pathlib import Path

import pytest
from conftest import conexao
from sqlalchemy import text

from jeje.dados import manifesto
from jeje.dados.carga import CargaInvalida, carregar
from jeje.dados.raw import COLUNAS

RECLAMACOES_DIA_1 = "complaints/year=2025/month=03/day=10/complaints_20250310.csv"
RECLAMACOES_DIA_2 = "complaints/year=2025/month=03/day=11/complaints_20250311.csv"
TEXTO_DIFICIL = 'Cobrança "duplicada", não reconhecida;\nvalor: 1.234,56 — ¿por qué?'


def escrever_csv(raiz: Path, caminho: str, tabela: str, registros: list[dict]) -> None:
    """CSV como os do desafio: BOM, todas as colunas da tabela, campos ausentes vazios."""
    buffer = io.StringIO()
    escritor = csv.writer(buffer, lineterminator="\n")
    escritor.writerow(COLUNAS[tabela])
    for registro in registros:
        escritor.writerow([registro.get(coluna, "") for coluna in COLUNAS[tabela]])
    destino = raiz / caminho
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("﻿" + buffer.getvalue(), encoding="utf-8")


@pytest.fixture
def dataset(tmp_path):
    raiz, manifestos = tmp_path / "raw", tmp_path / "manifesto"
    escrever_csv(raiz, RECLAMACOES_DIA_1, "complaints", [
        {"complaint_id": "CMP-1", "customer_id": "CLI-A", "description": TEXTO_DIFICIL},
        {"complaint_id": "CMP-2", "customer_id": "CLI-B", "claimed_amount": "460.27"},
    ])  # fmt: skip
    escrever_csv(raiz, RECLAMACOES_DIA_2, "complaints", [{"complaint_id": "CMP-3"}])
    escrever_csv(raiz, "branches.csv", "branches", [{"branch_id": "SUC-1", "city": "Bogotá"}])

    def publicar(tabelas=("complaints", "branches")):
        manifesto.escrever(manifestos, manifesto.gerar(raiz, list(tabelas)))
        return manifestos

    return raiz, publicar


def contagens(settings) -> dict[str, int]:
    with conexao(settings) as con:
        return {
            tabela: con.execute(text(f"select count(*) from raw.{tabela}")).scalar_one()
            for tabela in ("complaints", "branches")
        }


def versao_no_banco(settings) -> tuple[str, str] | None:
    with conexao(settings) as con:
        return con.execute(text("select version, source from meta.dataset_version")).first()


def test_carga_grava_registros_texto_nulos_linhagem_e_versao(banco_migrado, dataset):
    raiz, publicar = dataset
    manifestos = publicar()
    resultado = carregar(banco_migrado, raiz, manifestos, ["complaints", "branches"], "fixture")

    assert resultado.carregou
    assert contagens(banco_migrado) == {"complaints": 3, "branches": 1}
    assert tuple(versao_no_banco(banco_migrado)) == (
        manifesto.versao(manifestos, ["complaints", "branches"]),
        "fixture",
    )
    with conexao(banco_migrado) as con:
        cmp1 = con.execute(
            text("select description, claimed_amount, _arquivo, _linha "
                 "from raw.complaints where complaint_id = 'CMP-1'")
        ).one()  # fmt: skip
        cmp3 = con.execute(
            text("select _arquivo, _linha from raw.complaints where complaint_id = 'CMP-3'")
        ).one()
    assert cmp1.description == TEXTO_DIFICIL
    assert cmp1.claimed_amount is None
    assert (cmp1._arquivo, cmp1._linha) == (RECLAMACOES_DIA_1, 1)
    assert (cmp3._arquivo, cmp3._linha) == (RECLAMACOES_DIA_2, 1)


def test_mesma_versao_nao_recarrega_nem_duplica(banco_migrado, dataset):
    raiz, publicar = dataset
    manifestos = publicar()
    carregar(banco_migrado, raiz, manifestos, ["complaints", "branches"], "fixture")
    segunda = carregar(banco_migrado, raiz, manifestos, ["complaints", "branches"], "fixture")
    assert not segunda.carregou
    assert contagens(banco_migrado) == {"complaints": 3, "branches": 1}


def test_nova_versao_substitui_a_anterior_sem_sobras(banco_migrado, dataset):
    raiz, publicar = dataset
    carregar(banco_migrado, raiz, publicar(), ["complaints", "branches"], "fixture")
    escrever_csv(raiz, RECLAMACOES_DIA_2, "complaints", [{"complaint_id": "CMP-9"}])
    manifestos = publicar()
    resultado = carregar(banco_migrado, raiz, manifestos, ["complaints", "branches"], "fixture")
    assert resultado.carregou
    with conexao(banco_migrado) as con:
        ids = set(con.execute(text("select complaint_id from raw.complaints")).scalars())
    assert ids == {"CMP-1", "CMP-2", "CMP-9"}
    assert versao_no_banco(banco_migrado)[0] == resultado.versao


def test_falha_no_meio_da_carga_mantem_a_versao_anterior_inteira(banco_migrado, dataset):
    raiz, publicar = dataset
    anterior = carregar(banco_migrado, raiz, publicar(), ["complaints", "branches"], "fixture")
    # Nova versão cujo manifesto promete mais registros do que o 2º arquivo tem.
    escrever_csv(raiz, RECLAMACOES_DIA_2, "complaints", [{"complaint_id": "CMP-9"}])
    manifestos = publicar()
    caminho = manifestos / "complaints.csv"
    linhas = caminho.read_text().splitlines()
    linhas[-1] = linhas[-1].rsplit(",", 1)[0] + ",7"
    caminho.write_text("\n".join(linhas) + "\n")

    with pytest.raises(CargaInvalida, match="manifesto 7"):
        carregar(banco_migrado, raiz, manifestos, ["complaints", "branches"], "fixture")
    assert contagens(banco_migrado) == {"complaints": 3, "branches": 1}
    assert versao_no_banco(banco_migrado)[0] == anterior.versao


def test_arquivo_adulterado_e_recusado_antes_de_gravar(banco_migrado, dataset):
    raiz, publicar = dataset
    manifestos = publicar()
    alvo = raiz / "branches.csv"
    alvo.write_text(alvo.read_text(encoding="utf-8").replace("Bogotá", "Bogota"), encoding="utf-8")
    with pytest.raises(CargaInvalida, match=re.escape("branches.csv")):
        carregar(banco_migrado, raiz, manifestos, ["complaints", "branches"], "fixture")
    assert contagens(banco_migrado) == {"complaints": 0, "branches": 0}
    assert versao_no_banco(banco_migrado) is None


def test_tabela_fora_da_selecao_fica_vazia_na_nova_versao(banco_migrado, dataset):
    raiz, publicar = dataset
    carregar(banco_migrado, raiz, publicar(), ["complaints", "branches"], "fixture")
    carregar(banco_migrado, raiz, publicar(["branches"]), ["branches"], "fixture")
    assert contagens(banco_migrado) == {"complaints": 0, "branches": 1}


def test_registro_com_campos_a_menos_e_recusado_com_local_exato(banco_migrado, dataset):
    raiz, publicar = dataset
    alvo = raiz / RECLAMACOES_DIA_2
    alvo.write_text(alvo.read_text(encoding="utf-8") + "CMP-X,so-dois\n", encoding="utf-8")
    manifestos = publicar()
    esperado = re.escape(f"{RECLAMACOES_DIA_2}: registro 2 com 2 campos")
    with pytest.raises(CargaInvalida, match=esperado):
        carregar(banco_migrado, raiz, manifestos, ["complaints", "branches"], "fixture")
    assert versao_no_banco(banco_migrado) is None
