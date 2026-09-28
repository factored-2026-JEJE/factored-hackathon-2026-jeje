"""Versão do pipeline: muda com qualquer byte do código de dados e só com ele."""

import shutil

from jeje.dados import versao
from jeje.dados.versao import versao_pipeline


def test_versao_muda_com_o_conteudo_do_codigo_e_e_estavel_sem_mudanca(tmp_path):
    copia = tmp_path / "dados"
    shutil.copytree(versao.PACOTE, copia, ignore=shutil.ignore_patterns("__pycache__"))
    original = versao_pipeline(copia)
    assert versao_pipeline(copia) == original

    contratos = copia / "contratos.py"
    contratos.write_text(contratos.read_text().replace('"Suspended"', '"Suspendido"'))
    assert versao_pipeline(copia) != original
