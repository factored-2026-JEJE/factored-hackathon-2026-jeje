"""Catálogo ES/PT: paridade, ausência de promessas, valores exatos e cobertura da matriz."""

import re
from datetime import datetime
from decimal import Decimal

import pytest

from jeje import politica
from jeje.mensagens import (
    CLAUSULAS,
    IDIOMAS,
    MOTIVO_DO_CODIGO,
    TransacaoVerificada,
    compor,
    descrever,
    marcadores,
    valor,
)

# IDs da matriz de autonomia (backlog DEV-006) + mensagens de fluxo; escritos aqui como oráculo.
REGRAS_DA_MATRIZ = {
    "POL-CON-01", "POL-CON-02", "POL-CON-03", "POL-CON-04", "POL-CON-05", "POL-DISP-01",
    "POL-DISP-02", "POL-DISP-03", "POL-HUM-01", "POL-HUM-02", "POL-HUM-03", "POL-ESC-01",
    "POL-ID-02",
}  # fmt: skip

# Promessas que o atendimento automático não pode fazer (negações como "no es un reembolso" passam).
PROMESSAS = re.compile(
    r"reembolsar(emos|á)|devolver(emos|á)|recibirás|vas a recibir|você (vai )?receber|receberá"
    r"|garantiz|garantimos|em até \d|en hasta \d|dentro de \d|será estornad|vamos estornar",
    re.IGNORECASE,
)


def test_toda_regra_da_matriz_tem_clausula():
    assert set(CLAUSULAS) >= REGRAS_DA_MATRIZ


@pytest.mark.parametrize("clausula", sorted(CLAUSULAS))
def test_clausula_existe_nas_duas_linguas_com_os_mesmos_marcadores(clausula):
    assert set(CLAUSULAS[clausula]) == set(IDIOMAS)
    assert marcadores(clausula, "es") == marcadores(clausula, "pt")


@pytest.mark.parametrize("clausula", sorted(CLAUSULAS))
def test_nenhuma_clausula_promete_estorno_prazo_ou_resultado(clausula):
    for idioma in IDIOMAS:
        assert not PROMESSAS.search(CLAUSULAS[clausula][idioma]), (clausula, idioma)


def test_codigos_explicados_sao_exatamente_os_catalogados_pela_politica():
    assert set(MOTIVO_DO_CODIGO) == politica.CODIGOS_CATALOGADOS
    assert all(set(m) == set(IDIOMAS) for m in MOTIVO_DO_CODIGO.values())


@pytest.mark.parametrize(
    ("quantia", "moeda", "esperado"),
    [
        ("189900.55", "COP", "COP 189.900,55"),
        ("1234567.5", "USD", "USD 1.234.567,50"),
        ("0.05", "ARS", "ARS 0,05"),
        ("45.9", "USD", "USD 45,90"),
    ],
)
def test_valor_sempre_com_centavos_e_separadores_fixos(quantia, moeda, esperado):
    assert valor(Decimal(quantia), moeda) == esperado


TRANSACAO = TransacaoVerificada(
    "TRX-1",
    datetime(2025, 3, 10, 14, 9),
    Decimal("189900.55"),
    "COP",
    "Almacenes Éxito",
    "Declined",
)


def test_descricao_da_transacao_na_lingua_da_resposta():
    assert descrever(TRANSACAO, "es") == "en Almacenes Éxito de COP 189.900,55 (10/03/2025)"
    assert descrever(TRANSACAO, "pt") == "em Almacenes Éxito de COP 189.900,55 (10/03/2025)"


def test_compor_preenche_so_com_os_fatos_pedidos():
    texto = compor("POL-CON-03", "pt", transacao=descrever(TRANSACAO, "pt"), codigo="51",
                   motivo=MOTIVO_DO_CODIGO["51"]["pt"])  # fmt: skip
    assert texto == (
        "A transação em Almacenes Éxito de COP 189.900,55 (10/03/2025) foi recusada. Motivo "
        "informado no código 51: saldo insuficiente (significado genérico do padrão ISO 8583)."
    )


@pytest.mark.parametrize(
    "fatos",
    [{}, {"transacao": "x"}, {"transacao": "x", "codigo": "51", "motivo": "m", "extra": "e"}],
    ids=["nenhum", "faltando", "sobrando"],
)
def test_compor_recusa_marcador_faltando_ou_sobrando(fatos):
    with pytest.raises(ValueError, match="POL-CON-03"):
        compor("POL-CON-03", "es", **fatos)
