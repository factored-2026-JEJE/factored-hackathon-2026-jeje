"""Detector da garantia de encaminhamento da fraude (DEV-046), lado do treino: as frases com o
rótulo da validação, a temperatura, o limiar conformal por idioma e o artefato. Com o codificador
falso e determinístico dos testes do leitor (a imagem de testes não tem o e5): o que se testa é o
código da garantia, não os pesos."""

from collections import Counter

import numpy as np
import pytest
from test_leitor_treino import FRASES, codificar

from jeje.leitor.corpus import Corpus, Exemplo
from jeje.leitor.garantia import (
    ALFA,
    CLASSES,
    Garantia,
    Mensagem,
    do_corpus,
    golpes,
    metade_de_calibracao,
    posicoes_de_calibracao,
    quantil,
)
from jeje.leitor.modelo import ModeloInvalido

# Um rótulo do BANKING77 para cada fluxo das frases do leitor (o da validação decide a classe).
ROTULO = {
    "explicar_recusa": "declined_card_payment", "explicar_pendencia": "pending_transfer",
    "explicar_estorno": "reverted_card_payment?", "ver_transacoes": "card_arrival",
    "abrir_disputa": "card_payment_not_recognised", "relato_de_fraude": "lost_or_stolen_card",
    "fora_de_escopo": "exchange_rate",
}  # fmt: skip
TREINO = [Exemplo(t, fluxo, "es", intencao=ROTULO[fluxo])
          for fluxo, ts in FRASES.items() for t in ts]  # fmt: skip
# Golpe que o corpus não tem: a validação o gerou (NOV-31), e só a garantia o aprende.
GERADAS = [
    Mensagem("me llamaron del banco y les di el codigo", "fraude", "es"),
    Mensagem("um falso atendente pediu o codigo e eu passei", "fraude", "pt"),
    Mensagem("me hice una transferencia a un estafador", "fraude", "es"),
    Mensagem("cai num golpe do pix e perdi o dinheiro", "fraude", "pt"),
]
# Teste com as mesmas posições nas duas línguas: as fraudes calibram o limiar de cada uma.
FRAUDES = {
    "es": ["me robaron la tarjeta ayer", "clonaron mi tarjeta otra vez", "robaron mi celular hoy",
           "me llamaron del banco y les di la clave", "me robaron la tarjeta en el bus",
           "clonaron mi tarjeta de credito", "les di el codigo a un estafador",
           "robaron mi celular con la app", "me robaron la tarjeta y el celular",
           "me llamaron del banco y les di el codigo"],
    "pt": ["roubaram meu cartão ontem", "roubaram o celular hoje", "clonaram meu cartão",
           "um falso atendente pediu a senha", "roubaram meu cartão no ônibus",
           "clonaram meu cartão de crédito", "passei o codigo para um golpista",
           "roubaram o celular com o app", "roubaram meu cartão e o celular",
           "um falso atendente pediu o codigo"],
}  # fmt: skip
# Na posição 0 de cada língua, uma frase ambígua: o sorteio do limiar fica só com as outras.
AMBIGUAS = {"es": "perdí mi celular", "pt": "perdi meu celular"}
TESTE = [e for i, ts in FRAUDES.items() for e in (
    Exemplo(AMBIGUAS[i], "relato_de_fraude", i, intencao="lost_or_stolen_phone"),
    *(Exemplo(t, "relato_de_fraude", i, intencao="lost_or_stolen_card") for t in ts),
)]  # fmt: skip


@pytest.fixture(scope="module")
def garantia() -> Garantia:
    return Garantia.treinada(Corpus(TREINO, TREINO, TESTE), codificar, "v-teste", GERADAS)


def test_treino_so_com_frases_es_e_pt_do_banking77_e_o_rotulo_da_validacao():
    exemplos = [
        Exemplo("me robaron la tarjeta", "relato_de_fraude", "es", intencao="lost_or_stolen_card"),
        Exemplo("perdi meu celular", "relato_de_fraude", "pt", intencao="lost_or_stolen_phone"),
        Exemplo("mi transferencia falló", "fora_de_escopo", "es", intencao="failed_transfer"),
        Exemplo("someone stole my card", "relato_de_fraude", "en", intencao="lost_or_stolen_card"),
        Exemplo("congelar la tarjeta", "relato_de_fraude", "es", "minds14", "freeze"),
    ]
    assert do_corpus(exemplos) == [
        Mensagem("me robaron la tarjeta", "fraude", "es"),
        Mensagem("mi transferencia falló", "consultar", "es"),  # o celular perdido é ambíguo
    ]


def test_garantia_le_golpe_gerado_como_fraude_e_consulta_nao(garantia):
    golpe, consulta = garantia.p_fraude(
        codificar(["me llamaron del banco y les di el codigo", "pago rechazado"])
    )
    assert golpe > 0.5 > consulta


def test_limiar_cobre_as_fraudes_da_calibracao_por_idioma(garantia):
    """O limiar é a p(fraude) de uma das fraudes sorteadas para calibrar, e pelo menos 1 - alfa
    delas (com a correção de amostra finita) ficam acima dele."""
    sorteadas = metade_de_calibracao(range(1, len(FRAUDES["es"]) + 1))
    for idioma, textos in FRAUDES.items():
        calibracao = [t for k, t in enumerate(textos, start=1) if k in sorteadas]
        p = garantia.p_fraude(codificar(calibracao))
        limiar = garantia.limiares[idioma]
        assert limiar == round(1 - quantil((1 - p).tolist(), ALFA), 4)
        assert min(abs(p - limiar)) < 1e-4
        assert (p >= limiar - 1e-4).mean() >= 1 - ALFA


def test_temperatura_ajustada_na_calibracao():
    """Rótulos da calibração trocados: o detector acerta o treino com confiança e erra a
    calibração; a temperatura que minimiza a perda achata as probabilidades (T > 1)."""
    trocados = [Exemplo(e.texto, e.fluxo, "es", intencao="exchange_rate"
                        if e.intencao == "lost_or_stolen_card" else "lost_or_stolen_card")
                for e in TREINO]  # fmt: skip
    detector = Garantia.treinada(Corpus(TREINO, trocados, TESTE), codificar, "v", GERADAS)
    assert detector.temperatura > 1.5


def test_metade_de_calibracao_sorteia_so_entre_as_posicoes_dadas():
    posicoes = [0, 2, 3, 5, 8, 9, 11, 12]
    sorteio = metade_de_calibracao([*posicoes, 2, 3])  # repetidas contam uma vez
    assert len(sorteio) == 4 and sorteio <= set(posicoes)
    assert sorteio == metade_de_calibracao(list(reversed(posicoes)))  # a semente fixa o sorteio


def test_calibracao_so_sorteia_posicoes_de_frases_nao_ambiguas():
    # Posições pares ambíguas nas duas línguas: o sorteio fica só com as ímpares.
    rotulos = {(i, k): (None if k % 2 == 0 else "fraude") for i in ("es", "pt") for k in range(40)}
    sorteadas = posicoes_de_calibracao(rotulos)
    assert len(sorteadas) == 10 and all(k % 2 == 1 for k in sorteadas)


def test_quantil_com_a_correcao_de_amostra_finita():
    escores = [0.1 * k for k in range(1, 10)]  # 9 escores: posição teto(10 * 0,9) = 9
    assert quantil(escores, 0.10) == pytest.approx(0.9)
    assert quantil(escores, 0.5) == pytest.approx(0.5)  # teto(10 * 0,5) = 5


def test_treino_sem_alguma_classe_e_recusado():
    sem_fora = [e for e in TREINO if e.intencao not in ("exchange_rate", "card_arrival")]
    with pytest.raises(ModeloInvalido, match="classes"):
        Garantia.treinada(Corpus(sem_fora, sem_fora, TESTE), codificar, "v", [])


def test_artefato_da_garantia_salvo_e_carregado_le_igual(tmp_path, garantia):
    garantia.salvar(tmp_path / "garantia.joblib")
    lida = Garantia.carregar(tmp_path / "garantia.joblib")
    vetores = codificar(["me robaron la tarjeta", "pago rechazado"])
    assert np.allclose(lida.p_fraude(vetores), garantia.p_fraude(vetores))
    assert (lida.limiares, lida.versao) == (garantia.limiares, "v-teste")
    with pytest.raises(ModeloInvalido, match="ausente"):
        Garantia.carregar(tmp_path / "nao-existe.joblib")
    garantia.limiares.pop("pt")
    garantia.salvar(tmp_path / "sem-pt.joblib")
    with pytest.raises(ModeloInvalido, match="limiar"):
        Garantia.carregar(tmp_path / "sem-pt.joblib")


def test_golpes_versionados_estao_nas_classes_e_nas_duas_linguas():
    mensagens = golpes()
    assert len(mensagens) == 497
    assert {m.intencao for m in mensagens} <= set(CLASSES)
    assert Counter(m.idioma for m in mensagens).keys() == {"es", "pt"}
