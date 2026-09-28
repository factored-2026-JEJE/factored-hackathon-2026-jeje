"""Propriedade da carga raw: qualquer texto do arquivo volta do banco exatamente igual.

Alfabeto força os casos perigosos (acentos ES/PT, aspas, vírgula, ponto e vírgula, \\r, \\n, tab,
barra invertida) misturados a Unicode arbitrário. Exclui NUL (PostgreSQL não armazena \\x00 em
text) e surrogates (não codificáveis em UTF-8); texto vazio vira NULL por decisão da camada raw.
"""

import tempfile
from pathlib import Path

from conftest import conexao
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from test_carga import escrever_csv

from jeje.dados import manifesto
from jeje.dados.carga import carregar

PERIGOSOS = list("áéíóúâêôãõçñüÁÉÍÓÚÇÑ¿¡\"',;\n\r\t\\ ")
TEXTO = st.text(
    alphabet=st.one_of(
        st.sampled_from(PERIGOSOS),
        st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    ),
    min_size=1,
    max_size=60,
)


@settings(
    max_examples=40,
    deadline=None,
    # O banco é recriado por teste, não por exemplo: cada exemplo é uma nova versão carregada.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(textos=st.lists(TEXTO, min_size=1, max_size=15))
def test_texto_arbitrario_volta_do_banco_identico(banco_migrado, textos):
    with tempfile.TemporaryDirectory() as tmp:
        raiz, manifestos = Path(tmp) / "raw", Path(tmp) / "manifesto"
        registros = [
            {"complaint_id": f"CMP-{i}", "description": texto} for i, texto in enumerate(textos)
        ]
        escrever_csv(raiz, "complaints/year=2025/month=03/day=10/c.csv", "complaints", registros)
        manifesto.escrever(manifestos, manifesto.gerar(raiz, ["complaints"]))
        carregar(banco_migrado, raiz, manifestos, ["complaints"], "fixture")

    with conexao(banco_migrado) as con:
        no_banco = dict(
            con.execute(text("select complaint_id, description from raw.complaints")).all()
        )
    assert no_banco == {f"CMP-{i}": texto for i, texto in enumerate(textos)}
