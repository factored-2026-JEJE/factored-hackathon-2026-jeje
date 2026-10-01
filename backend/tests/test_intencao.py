"""Portão de intenção de Enzo (TF-IDF, incorporado pela PRD-009): modelo e rotas HTTP.

Os testes do modelo e das rotas são os da branch dele (tag `arquivo/intencao-classificador`), com o
corpus e os fluxos do leitor (que sucederam os do portão) e um artefato treinado aqui num corpus
pequeno: a imagem de teste não tem o do build. Os testes do corpus ficaram com o leitor
(`test_leitor_treino.py`).
"""

import joblib
import pytest
from conftest import cliente
from hypothesis import given, settings
from hypothesis import strategies as st

from jeje.config import Settings
from jeje.intencao import __main__ as cli
from jeje.intencao.modelo import Classificador, ModeloInvalido, avaliar, treinar, versao
from jeje.leitor.corpus import Corpus, Exemplo
from jeje.leitor.fontes import Arquivo, FonteInvalida

FRASES = {
    "explicar_recusa": ["me rechazaron la tarjeta", "pago rechazado", "cartão recusado",
                        "compra recusada", "card declined", "transacción rechazada"],
    "explicar_pendencia": ["transferencia pendiente", "pagamento pendente", "pending transfer",
                           "compra pendiente", "saque pendente", "payment pending"],
    "explicar_estorno": ["reembolso no aparece", "estorno não caiu", "refund not showing",
                         "reembolso no llega", "estorno sumiu", "refund missing"],
    "abrir_disputa": ["no reconozco este cargo", "não reconheço a compra", "charged twice",
                      "cargo no reconocido", "cobrança não reconhecida", "unrecognised charge"],
    "relato_de_fraude": ["me robaron la tarjeta", "roubaram meu cartão", "card stolen",
                         "robaron mi celular", "roubaram o celular", "stolen phone"],
    "fora_de_escopo": ["quiero ver mi saldo", "aumentar limite", "cambiar el pin",
                       "ver saldo da conta", "mudar a senha", "exchange rate"],
}  # fmt: skip
EXEMPLOS = [Exemplo(t, fluxo, "es") for fluxo, textos in FRASES.items() for t in textos]
FONTES = (Arquivo("teste.csv", "file:///teste.csv", 1, "a" * 64),)


@pytest.fixture(scope="module")
def pequeno() -> Classificador:
    return Classificador.treinado(
        Corpus(treino=EXEMPLOS, calibracao=[], teste=EXEMPLOS), fontes=FONTES
    )


@pytest.fixture
def com_modelo(pequeno, tmp_path) -> Settings:
    pequeno.salvar(tmp_path / "intencao.joblib")
    return Settings().model_copy(update={"intencao_modelo": tmp_path / "intencao.joblib"})


# ---- modelo ----


def test_classifica_mensagens_obvias_do_corpus_pequeno(pequeno):
    assert pequeno.classificar("rechazaron mi pago").fluxo == "explicar_recusa"
    assert pequeno.classificar("roubaram meu celular").fluxo == "relato_de_fraude"
    assert pequeno.classificar("não reconheço esse cargo").fluxo == "abrir_disputa"


def test_previsao_traz_todos_os_fluxos_em_ordem_decrescente_somando_um(pequeno):
    previsao = pequeno.classificar("reembolso pendiente")
    probs = [p.probabilidade for p in previsao.probabilidades]
    assert sorted(p.fluxo for p in previsao.probabilidades) == sorted(FRASES)
    assert probs == sorted(probs, reverse=True)
    assert sum(probs) == pytest.approx(1, abs=1e-3)


@settings(max_examples=40, deadline=None)
@given(texto=st.text(min_size=1, max_size=200))
def test_qualquer_texto_tem_fluxo_igual_ao_mais_provavel(pequeno, texto):
    previsao = pequeno.classificar(texto)
    assert previsao.fluxo == previsao.probabilidades[0].fluxo
    assert previsao.confianca == previsao.probabilidades[0].probabilidade


def test_fluxos_em_lote_dao_o_mesmo_que_um_a_um(pequeno):
    textos = ["pago rechazado", "roubaram meu cartão", "quiero ver mi saldo"]
    um_a_um = [(p.fluxo, p.confianca) for p in map(pequeno.classificar, textos)]
    em_lote = [(fluxo, round(confianca, 4)) for fluxo, confianca in pequeno.fluxos(textos)]
    assert em_lote == um_a_um


def test_sinais_sao_trechos_da_propria_mensagem_que_favorecem_o_fluxo(pequeno):
    texto = "me rechazaron la tarjeta"
    previsao = pequeno.classificar(texto)
    assert previsao.sinais
    assert all(s.replace("_", " ") in f" {texto} " for s in previsao.sinais)
    assert any("rech" in s for s in previsao.sinais)


def test_salvar_e_carregar_preservam_previsoes_e_versao(pequeno, tmp_path):
    pequeno.salvar(tmp_path / "m.joblib")
    carregado = Classificador.carregar(tmp_path / "m.joblib")
    assert carregado.classificar("pago rechazado") == pequeno.classificar("pago rechazado")
    assert carregado.metadados == pequeno.metadados


def test_carregar_recusa_artefato_ausente_ou_de_outro_formato(tmp_path):
    with pytest.raises(ModeloInvalido, match="ausente"):
        Classificador.carregar(tmp_path / "nao-existe.joblib")
    joblib.dump({"outra": "coisa"}, tmp_path / "estranho.joblib")
    with pytest.raises(ModeloInvalido, match="formato"):
        Classificador.carregar(tmp_path / "estranho.joblib")


def test_versao_muda_quando_uma_fonte_muda():
    outra = (Arquivo("teste.csv", "file:///teste.csv", 1, "f" * 64),)
    assert versao(FONTES) == versao(FONTES)
    assert versao(outra) != versao(FONTES)


def test_avaliar_separa_metricas_por_idioma():
    pipeline = treinar(EXEMPLOS)
    teste = [
        Exemplo("pago rechazado", "explicar_recusa", "es"),
        Exemplo("card stolen", "explicar_recusa", "en"),
    ]  # o segundo está rotulado errado de propósito
    metricas = avaliar(pipeline, teste)
    assert (metricas["es"].exemplos, metricas["es"].acuracia) == (1, 1.0)
    assert (metricas["en"].exemplos, metricas["en"].acuracia) == (1, 0.0)


def test_cli_sem_argumentos_mostra_uso_e_erro_de_corpus_sai_com_1(monkeypatch, tmp_path):
    assert cli.main(["jeje.intencao"]) == 2

    # Fronteira de rede simulada (ENG-006): o download do corpus falha.
    def falha(*_):
        raise FonteInvalida("fonte indisponível")

    monkeypatch.setattr(cli.fontes, "baixar", falha)
    assert cli.main(["jeje.intencao", "treinar", str(tmp_path), str(tmp_path / "m.joblib")]) == 1


# ---- rotas ----


def test_rota_classifica_recusa_em_espanhol_e_fraude_em_portugues(com_modelo):
    with cliente(com_modelo) as http:
        recusa = http.post("/intencao/classificar", json={"texto": "me rechazaron el pago"})
        fraude = http.post("/intencao/classificar", json={"texto": "roubaram meu cartão ontem"})
    assert recusa.status_code == 200
    assert recusa.json()["fluxo"] == "explicar_recusa"
    assert fraude.json()["fluxo"] == "relato_de_fraude"


def test_rota_recusa_texto_vazio_so_espacos_ou_longo_demais(com_modelo):
    with cliente(com_modelo) as http:
        # O limite vale antes de tirar os espaços (U+0085 é espaço): caso achado pelo Schemathesis.
        for texto in ("", "   ", "x" * 1001, "\u0085" + "x" * 1000):
            assert http.post("/intencao/classificar", json={"texto": texto}).status_code == 422


def test_rota_responde_400_documentado_para_corpo_que_nao_e_utf8(com_modelo):
    with cliente(com_modelo) as http:
        resposta = http.post(
            "/intencao/classificar",
            content=b'{"texto": "\xff"}',  # UTF-8 inválido (caso achado pelo Schemathesis)
            headers={"content-type": "application/json"},
        )
        respostas = http.get("/openapi.json").json()["paths"]["/intencao/classificar"]["post"]
    assert resposta.status_code == 400
    assert "400" in respostas["responses"]


def test_rota_do_modelo_publica_a_versao_que_responde_as_previsoes(com_modelo):
    with cliente(com_modelo) as http:
        modelo = http.get("/intencao/modelo").json()
        previsao = http.post("/intencao/classificar", json={"texto": "transferencia pendiente"})
    assert previsao.json()["modelo"] == modelo["versao"]
    assert set(modelo["metricas_teste"]) == {"es"}


def test_sem_o_modelo_as_rotas_respondem_503_e_a_api_segue(tmp_path):
    """O original exigia o artefato para a API subir; incorporado, o portão fica indisponível e o
    resto segue, como o leitor."""
    sem = Settings().model_copy(update={"intencao_modelo": tmp_path / "ausente.joblib"})
    with cliente(sem) as http:
        modelo = http.get("/intencao/modelo")
        classificar = http.post("/intencao/classificar", json={"texto": "pago rechazado"})
        saude = http.get("/health")
    assert (modelo.status_code, classificar.status_code, saude.status_code) == (503, 503, 200)


def test_com_dois_fluxos_os_sinais_saem_do_fluxo_escolhido():
    """Com só dois fluxos, a regressão tem uma linha de pesos só: os sinais do outro fluxo são os
    mesmos pesos com o sinal trocado (achado pelo teste de contrato ao incorporar o portão)."""
    exemplos = [e for e in EXEMPLOS if e.fluxo in ("explicar_recusa", "relato_de_fraude")]
    dois = Classificador.treinado(
        Corpus(treino=exemplos, calibracao=[], teste=exemplos), fontes=FONTES
    )
    recusa, fraude = dois.classificar("pago rechazado"), dois.classificar("me robaron")
    assert (recusa.fluxo, fraude.fluxo) == ("explicar_recusa", "relato_de_fraude")
    assert any("rec" in s for s in recusa.sinais)
    assert any("rob" in s for s in fraude.sinais)
