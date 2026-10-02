"""Exemplos do LLM do "não entendi" (DEV-042): as frases do BANKING77 com o rótulo da validação e
o vetor do e5, e as mais parecidas com a mensagem.

O e5 é o codificador falso do treino do leitor (saco de palavras normalizado, determinístico): o que
se testa é a escolha das frases, não os pesos do modelo.
"""

import numpy as np
import pytest
from test_leitor_treino import codificar

from jeje.leitor import vizinhos
from jeje.leitor.codificador import ComMemoria
from jeje.leitor.corpus import Exemplo
from jeje.leitor.vizinhos import Vizinhos, VizinhosInvalidos

# Duas frases de cada intenção em cada idioma, uma ambígua, uma do inglês e uma do MInDS-14.
CORPUS = [
    Exemplo("rechazaron mi tarjeta en la tienda", "explicar_recusa", "es",
            intencao="declined_card_payment"),
    Exemplo("mi transferencia falló otra vez", "fora_de_escopo", "es", intencao="failed_transfer"),
    Exemplo("no reconozco este cargo", "abrir_disputa", "es",
            intencao="card_payment_not_recognised"),
    Exemplo("me cobraron dos veces", "abrir_disputa", "es", intencao="transaction_charged_twice"),
    Exemplo("me robaron la tarjeta", "relato_de_fraude", "es", intencao="lost_or_stolen_card"),
    Exemplo("creo que clonaron mi tarjeta", "relato_de_fraude", "es", intencao="compromised_card"),
    Exemplo("cuándo llega mi tarjeta nueva", "fora_de_escopo", "es", intencao="card_arrival"),
    Exemplo("cuál es el tipo de cambio", "fora_de_escopo", "es", intencao="exchange_rate"),
    Exemplo("quiero un reembolso de la compra", "abrir_disputa", "es", intencao="request_refund"),
    Exemplo("perdí mi celular", "relato_de_fraude", "es", intencao="lost_or_stolen_phone"),
    Exemplo("meu cartão foi recusado na loja", "explicar_recusa", "pt",
            intencao="declined_card_payment"),
    Exemplo("minha transferência está pendente", "explicar_pendencia", "pt",
            intencao="pending_transfer"),
    Exemplo("não reconheço essa cobrança", "abrir_disputa", "pt",
            intencao="card_payment_not_recognised"),
    Exemplo("tem um saque que eu não fiz", "abrir_disputa", "pt",
            intencao="cash_withdrawal_not_recognised"),
    Exemplo("roubaram meu cartão", "relato_de_fraude", "pt", intencao="lost_or_stolen_card"),
    Exemplo("acho que clonaram meu cartão", "relato_de_fraude", "pt", intencao="compromised_card"),
    Exemplo("quando chega meu cartão novo", "fora_de_escopo", "pt", intencao="card_arrival"),
    Exemplo("qual é a cotação do câmbio", "fora_de_escopo", "pt", intencao="exchange_rate"),
    Exemplo("someone stole my card", "relato_de_fraude", "en", intencao="lost_or_stolen_card"),
    Exemplo("quiero congelar mi tarjeta", "relato_de_fraude", "es", "minds14", "freeze"),
]  # fmt: skip


@pytest.fixture(scope="module")
def exemplos() -> Vizinhos:
    return Vizinhos.dos_exemplos(CORPUS, codificar, "v-teste")


def test_rotulo_das_frases_e_o_pre_registrado_pela_validacao():
    assert vizinhos.intencao("declined_card_payment") == "consultar"
    # Transferência que falhou é consulta no prompt (no leitor, o fluxo é fora de escopo).
    assert vizinhos.intencao("failed_transfer") == "consultar"
    assert vizinhos.intencao("transaction_charged_twice") == "contestar"
    assert vizinhos.intencao("compromised_card") == "fraude"
    assert vizinhos.intencao("card_arrival") == "fora_de_escopo"
    assert vizinhos.intencao("request_refund") is None
    assert vizinhos.intencao("lost_or_stolen_phone") is None


def test_so_frases_do_banking77_em_es_e_pt_sem_as_ambiguas(exemplos):
    assert exemplos.textos == {
        ("es", "consultar"): ["rechazaron mi tarjeta en la tienda",
                              "mi transferencia falló otra vez"],
        ("es", "contestar"): ["no reconozco este cargo", "me cobraron dos veces"],
        ("es", "fraude"): ["me robaron la tarjeta", "creo que clonaron mi tarjeta"],
        ("es", "fora_de_escopo"): ["cuándo llega mi tarjeta nueva", "cuál es el tipo de cambio"],
        ("pt", "consultar"): ["meu cartão foi recusado na loja",
                              "minha transferência está pendente"],
        ("pt", "contestar"): ["não reconheço essa cobrança", "tem um saque que eu não fiz"],
        ("pt", "fraude"): ["roubaram meu cartão", "acho que clonaram meu cartão"],
        ("pt", "fora_de_escopo"): ["quando chega meu cartão novo", "qual é a cotação do câmbio"],
    }  # fmt: skip
    for chave, textos in exemplos.textos.items():
        assert np.array_equal(exemplos.vetores[chave], codificar(textos))


@pytest.mark.parametrize(
    ("idioma", "intencao", "mensagem"),
    [
        ("es", "fraude", "creo que clonaron mi tarjeta"),
        ("es", "consultar", "mi transferencia falló otra vez"),
        ("pt", "contestar", "tem um saque que eu não fiz"),
    ],
)
def test_mais_parecidas_de_cada_intencao_no_idioma_da_mensagem(exemplos, idioma, intencao,
                                                               mensagem):  # fmt: skip
    (vetor,) = codificar([mensagem])
    parecidas = exemplos.mais_parecidos(vetor, idioma)
    # A frase igual à mensagem é a mais parecida da intenção dela.
    assert parecidas[intencao][0] == mensagem
    assert list(parecidas) == ["consultar", "contestar", "fora_de_escopo", "fraude"]
    for lida, frases in parecidas.items():
        assert sorted(frases) == sorted(exemplos.textos[idioma, lida])  # k = 3 > 2 frases
        cossenos = [float(codificar([f])[0] @ vetor) for f in frases]
        assert cossenos == sorted(cossenos, reverse=True)
    assert exemplos.mais_parecidos(vetor, idioma, k=1)[intencao] == [mensagem]


def test_sem_frases_de_alguma_intencao_em_algum_idioma_e_erro():
    sem_fraude_pt = [e for e in CORPUS if not (e.idioma == "pt" and e.fluxo == "relato_de_fraude")]
    with pytest.raises(VizinhosInvalidos, match="fraude em pt"):
        Vizinhos.dos_exemplos(sem_fraude_pt, codificar, "v")


def test_artefato_salvo_e_carregado_acha_as_mesmas_frases(tmp_path, exemplos):
    exemplos.salvar(tmp_path / "vizinhos.joblib")
    carregado = Vizinhos.carregar(tmp_path / "vizinhos.joblib")
    (vetor,) = codificar(["me cobraron dos veces la compra"])
    assert carregado.mais_parecidos(vetor, "es") == exemplos.mais_parecidos(vetor, "es")
    assert carregado.versao == "v-teste"


def test_artefato_ausente_de_outro_formato_ou_incompleto_e_recusado(tmp_path, exemplos):
    import joblib

    with pytest.raises(VizinhosInvalidos, match="ausente"):
        Vizinhos.carregar(tmp_path / "nao-existe.joblib")
    joblib.dump({"formato": 99}, tmp_path / "velho.joblib")
    with pytest.raises(VizinhosInvalidos, match="formato"):
        Vizinhos.carregar(tmp_path / "velho.joblib")
    cortado = {chave: v[:1] for chave, v in exemplos.vetores.items()}
    joblib.dump({"formato": 1, "textos": exemplos.textos, "vetores": cortado, "versao": "v"},
                tmp_path / "cortado.joblib")  # fmt: skip
    with pytest.raises(VizinhosInvalidos, match="não batem"):
        Vizinhos.carregar(tmp_path / "cortado.joblib")


def test_versao_muda_com_o_leitor():
    assert vizinhos.versao("a" * 64) == vizinhos.versao("a" * 64)
    assert vizinhos.versao("a" * 64) != vizinhos.versao("b" * 64)


def test_com_memoria_cada_texto_e_codificado_uma_vez_so():
    pedidos = []

    def contando(textos):
        pedidos.append(list(textos))
        return codificar(textos)

    memoria = ComMemoria(contando)
    primeiro = memoria(["a b", "c", "a b"])
    segundo = memoria(["c", "d e"])
    assert pedidos == [["a b", "c"], ["d e"]]
    assert np.array_equal(primeiro, codificar(["a b", "c", "a b"]))
    assert np.array_equal(segundo, codificar(["c", "d e"]))
