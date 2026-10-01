"""Qual transação o cliente descreve (DEV-037): concordância com as pistas, ranking, conjunto
conformal, a pergunta pelo campo que mais divide e a calibração, que só grava agregados."""

import json
import random
from datetime import date, datetime
from decimal import Decimal

import numpy as np
import pytest
from conftest import conexao, curar_tudo, raw_cliente, raw_produto, raw_transacao

from jeje import calibrar_qual_transacao as calibracao_cli
from jeje.interpretacao import interpretar
from jeje.politica import Candidata, Pista
from jeje.qual_transacao import (
    ATRIBUTOS,
    Calibracao,
    atributos,
    campo_que_mais_divide,
    concorda,
    limiar,
    probabilidades,
    resolver,
    tem_pista,
    treinar,
)

HOJE = date(2025, 3, 31)
STREAMING = Candidata("T1", Decimal("45.90"), datetime(2025, 3, 10, 14, 9), "Streaming Plus")
UBER = Candidata("T2", Decimal("20.00"), datetime(2025, 3, 14, 18, 30), "Uber")
FARMACIA = Candidata("T3", Decimal("46.10"), datetime(2025, 3, 11, 9, 0), "Farmacia Salud")


def coluna(x: np.ndarray, nome: str) -> list[float]:
    return list(x[:, ATRIBUTOS.index(nome)])


def test_atributos_medem_a_concordancia_com_cada_pista():
    pista = Pista(Decimal("45.90"), date(2025, 3, 10), "Streaming Plus")
    x = atributos([STREAMING, UBER, FARMACIA], pista, HOJE)
    assert coluna(x, "valor_igual") == [1, 0, 0]
    assert coluna(x, "data_dentro") == [1, 0, 0]
    assert coluna(x, "comercio") == [1, 0, 0]
    # 46,10 está mais perto de 45,90 que 20,00; a Farmacia é de um dia depois.
    assert coluna(x, "valor_perto")[2] > coluna(x, "valor_perto")[1]
    assert coluna(x, "data_distancia")[2] == pytest.approx(-1 / 7)


def test_sem_pista_so_a_recencia_conta():
    x = atributos([STREAMING, UBER], Pista(), HOJE)
    assert not tem_pista(Pista()) and tem_pista(Pista(comercio="Uber"))
    assert not x[:, :-1].any()
    assert coluna(x, "recencia")[1] > coluna(x, "recencia")[0]  # a de Uber é mais recente


def test_treino_aprende_a_preferir_a_candidata_que_concorda_com_as_pistas():
    candidatas = [STREAMING, UBER, FARMACIA]
    casos = [(atributos(candidatas, Pista(c.amount), HOJE), i) for i, c in enumerate(candidatas)]
    pesos = treinar(casos * 5)
    for x, certa in casos:
        assert int(np.argmax(probabilidades(x, pesos))) == certa


def test_limiar_conformal_com_a_correcao_de_amostra_finita():
    escores = [i / 10 for i in range(10)]  # 0,0 a 0,9
    # n = 10 e alfa = 0,2: a posição teto(11 x 0,8) = 9, o 9º menor escore.
    assert limiar(escores, 0.2) == 0.8
    assert limiar(escores, 0.01) == 0.9  # além do fim, o maior


def test_conjunto_guarda_as_provaveis_da_mais_para_a_menos_provavel():
    pesos = tuple(1.0 if nome == "valor_perto" else 0.0 for nome in ATRIBUTOS)
    calibracao = Calibracao("v", 0.05, pesos, {"es": 0.95})
    x = atributos([UBER, STREAMING, FARMACIA], Pista(Decimal("46.05")), HOJE)
    # 46,10 e 45,90 ficam (a de 46,10, mais perto, primeiro); 20,00 fica de fora.
    assert calibracao.conjunto(x, "es", [0, 1, 2]) == [2, 1]
    # A probabilidade é entre as aceitas: só a de 45,90 aceita, ela leva tudo.
    assert calibracao.ordem(x, [1]) == [(1, pytest.approx(1.0))]


def test_comercio_citado_decide_quem_pode_ser_valor_e_data_se_dizem_de_cabeca():
    assert concorda(STREAMING, Pista(Decimal("50"), comercio="Streaming Plus"))
    assert not concorda(FARMACIA, Pista(Decimal("46.10"), comercio="Streaming Plus"))
    assert concorda(FARMACIA, Pista(Decimal("42.00")))  # a até 10%
    assert not concorda(UBER, Pista(Decimal("42.00")))
    assert concorda(UBER, Pista(data=date(2025, 3, 21)))  # a até 7 dias
    assert not concorda(UBER, Pista(data=date(2025, 3, 22)))


CALIBRACAO = Calibracao(
    "v",
    0.05,
    tuple(1.0 if n in ("valor_perto", "comercio") else 0.0 for n in ATRIBUTOS),
    {"es": 0.05},
)


def resolver_es(candidatas, pista):
    return resolver(candidatas, pista, CALIBRACAO, "es", HOJE, 5)


def test_uma_so_possivel_com_garantia_segue_e_sem_garantia_mostra_as_possiveis():
    # O comércio citado deixa uma só possível: segue com ela, mesmo com o valor de cabeça.
    unica = resolver_es(
        [STREAMING, FARMACIA, UBER], Pista(Decimal("50"), comercio="Streaming Plus")
    )
    assert (unica.tipo, unica.transacoes) == ("unica", ("T1",))
    # Duas parecidas (45,90 e 46,10 para "46"): sem garantia de uma, as duas viram botões.
    varias = resolver_es([STREAMING, FARMACIA, UBER], Pista(Decimal("46")))
    assert (varias.tipo, set(varias.transacoes), varias.campo) == ("varias", {"T1", "T3"}, None)
    # Nenhuma possível: pede dados, como o filtro.
    assert resolver_es([UBER], Pista(Decimal("500"))).tipo == "nenhuma"
    # "A última": a mais recente das possíveis (as candidatas vêm das mais recentes primeiro).
    ultima = resolver_es([FARMACIA, STREAMING], Pista(Decimal("46"), ultima=True))
    assert (ultima.tipo, ultima.transacoes) == ("unica", ("T3",))


def test_numero_solto_vira_opcao_e_a_pista_que_nao_engana_segue_direto():
    """ACH-143: o número solto pode ser o dia ou o final do cartão: a única possível vira opção.
    Com o valor marcado, a data, o comércio ou "a última", segue direto."""
    solto = resolver_es([STREAMING, UBER], Pista(Decimal("46")))
    assert (solto.tipo, solto.transacoes) == ("varias", ("T1",))
    # O conjunto garante a de 45,90, mas o número solto não basta: as duas possíveis viram opção.
    perto = Candidata("T9", Decimal("48.00"), datetime(2025, 3, 12), "Loja 9")
    duas = resolver_es([STREAMING, perto], Pista(Decimal("46")))
    assert (duas.tipo, duas.transacoes) == ("varias", ("T1", "T9"))
    for pista in (
        Pista(Decimal("46"), valor_marcado=True),
        Pista(Decimal("46"), data=date(2025, 3, 10)),
        Pista(Decimal("46"), comercio="Streaming Plus"),
        Pista(Decimal("46"), ultima=True),
    ):
        direta = resolver_es([STREAMING, UBER], pista)
        assert (direta.tipo, direta.transacoes) == ("unica", ("T1",))


def test_com_mais_de_tres_possiveis_pergunta_pelo_campo_que_mais_divide():
    # Todas de 45,90: duas datas e cinco comércios. O comércio divide mais que a data.
    cinco_lojas = [
        Candidata(f"T{n}", Decimal("45.90"), datetime(2025, 3, 10 + n % 2), f"Loja {n}")
        for n in range(5)
    ]
    resolucao = resolver_es(cinco_lojas, Pista(Decimal("46")))
    assert (resolucao.tipo, len(resolucao.transacoes), resolucao.campo) == ("varias", 5, "comercio")
    # Cinco datas e duas lojas: a data dividiria mais, mas o cliente já a disse.
    cinco_dias = [
        Candidata(f"T{n}", Decimal("45.90"), datetime(2025, 3, 10 + n), f"Loja {n % 2}")
        for n in range(5)
    ]
    assert resolver_es(cinco_dias, Pista(Decimal("46"))).campo == "data"
    assert resolver_es(cinco_dias, Pista(Decimal("46"), data=date(2025, 3, 12))).campo == "comercio"


def test_pergunta_pelo_campo_que_mais_divide_as_candidatas():
    mesmo_valor = [
        STREAMING,
        Candidata("T4", Decimal("45.90"), datetime(2025, 3, 12), "Uber"),
        Candidata("T5", Decimal("45.90"), datetime(2025, 3, 12), "Uber"),
    ]
    pesos = np.array([1 / 3] * 3)
    # O valor não divide nada; data e comércio dividem igual, e a data vem primeiro.
    assert campo_que_mais_divide(mesmo_valor, pesos, [0, 1, 2]) == "data"
    # Só o comércio divide: a mesma data e o mesmo valor, comércios diferentes.
    mesmo_dia = [STREAMING, Candidata("T6", Decimal("45.90"), datetime(2025, 3, 10), "Uber")]
    assert campo_que_mais_divide(mesmo_dia, np.array([0.5, 0.5]), [0, 1]) == "comercio"
    # Nada divide: nenhuma pergunta.
    assert campo_que_mais_divide([STREAMING, STREAMING], np.array([0.5, 0.5]), [0, 1]) is None


@pytest.mark.parametrize("idioma", ["es", "pt"])
def test_descricao_sai_nos_formatos_que_a_conversa_le(idioma):
    """A calibração descreve o alvo e lê a frase com os extratores do produto: as pistas exatas
    sorteadas voltam iguais (valor e data); a de cabeça vem sem os centavos ou na dezena."""
    alvo = Candidata("T7", Decimal("1234.56"), datetime(2025, 3, 10, 9), None)
    lidas = [
        interpretar(calibracao_cli.descrever(alvo, idioma, HOJE, random.Random(n)), idioma, HOJE)
        for n in range(40)
    ]
    assert {lida.valor for lida in lidas} - {None} == {Decimal("1234.56"), 1235, 1230}
    assert {lida.data for lida in lidas} - {None} == {date(2025, 3, 10)}


def test_caso_da_calibracao_le_o_valor_marcado_como_a_conversa():
    """ACH-143: a calibração mede com a regra da conversa: o valor exato (com os centavos) é
    marcado e pode seguir direto; o de cabeça, não."""
    alvo = Candidata("T7", Decimal("1234.56"), datetime(2025, 3, 10, 9), None)
    casos = [
        calibracao_cli._caso(f"k{n}", "es", alvo, [alvo], HOJE, "historico") for n in range(40)
    ]
    lidas = {(c["pista"].valor, c["pista"].valor_marcado) for c in casos if c is not None}
    assert lidas - {(None, False)} == {
        (Decimal("1234.56"), True), (Decimal("1235"), False), (Decimal("1230"), False)
    }  # fmt: skip


@pytest.fixture
def muitos_clientes(banco_migrado):
    """40 clientes, cada um com três compras parecidas entre si (valor, data e comércio)."""
    with conexao(banco_migrado) as con:
        for n in range(40):
            cliente, produto = f"CLI-{n:03d}", f"PRD-{n:03d}"
            raw_cliente(con, cliente)
            raw_produto(con, produto, cliente)
            for k, (valor, comercio) in enumerate(
                (("45.90", "Streaming Plus"), ("46.10", "Uber"), ("189.77", "Farmacia Salud"))
            ):
                quando = f"2025-03-{10 + k + n % 5} 12:00:00"
                raw_transacao(
                    con, f"TRX-{n:03d}-{k}", cliente, produto, amount=valor, merchant_name=comercio,
                    transaction_type="Purchase", transaction_date=quando,
                )  # fmt: skip
    curar_tudo(banco_migrado)
    return banco_migrado


def test_calibracao_grava_so_agregados_e_mede_contra_o_filtro_de_hoje(muitos_clientes):
    with conexao(muitos_clientes) as con:
        resultado = calibracao_cli.calibrar(con, clientes=40)
    texto = json.dumps(resultado, ensure_ascii=False)
    # Nenhum registro de cliente: nem cliente, nem transação, nem comércio.
    assert not any(marca in texto for marca in ("CLI-", "TRX-", "PRD-", "Streaming", "Uber"))
    assert set(resultado["pesos"]) == set(ATRIBUTOS)
    assert set(resultado["limiares"]) == set(resultado["teste"]) == {"es", "pt"}
    assert resultado["clientes"] == 40 and all(resultado["casos"].values())
    for idioma in ("es", "pt"):
        assert set(resultado["teste"][idioma]) == {"historico", "denso"}
        assert set(resultado["teste"][idioma]["historico"]) == {
            "casos", "com_ranking", "filtro_exato"
        }  # fmt: skip
    # A versão é o hash do que determina a calibração: a mesma entrada dá a mesma.
    with conexao(muitos_clientes) as con:
        assert calibracao_cli.calibrar(con, clientes=40)["versao"] == resultado["versao"]


def test_cli_sem_arquivo_de_saida_mostra_o_uso():
    assert calibracao_cli.main(["jeje.calibrar_qual_transacao"]) == 2
