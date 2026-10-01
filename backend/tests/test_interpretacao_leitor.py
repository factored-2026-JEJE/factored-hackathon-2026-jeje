"""Interpretação com o leitor e5 (INTERPRETADOR=leitor): cascata atrás das regras.

O modelo é substituído por um leitor fixo (devolve o fluxo e a confiança que o teste define): o que
se testa é a cascata, o limite, o mapeamento, o fallback e o registro no turno. As regras, a
conversa e a política são o código real.
"""

import logging
from datetime import date

import pytest
from conftest import abrir_conversa, autenticar, cliente, conexao, dizer
from sqlalchemy import text

from jeje import interpretacao_modelo
from jeje.interpretacao_leitor import Leitor, dos_arquivos
from jeje.leitor.modelo import Leitura as LidaDoModelo

REFERENCIA = date(2026, 3, 1)
VAGA = "apareceu um negócio esquisito na minha fatura"


class ModeloFixo:
    versao = "abcdef0123456789"

    def __init__(self, fluxo: str, confianca: float, erro: Exception | None = None):
        self.fluxo, self.confianca, self.erro, self.lidos = fluxo, confianca, erro, []

    def ler(self, textos, _codificar):
        if self.erro is not None:
            raise self.erro
        self.lidos += list(textos)
        return [LidaDoModelo(self.fluxo, self.confianca) for _ in textos]


def leitor(fluxo="abrir_disputa", confianca=0.95, limite=0.8, erro=None, falha_na_carga=None):
    modelo, cargas = ModeloFixo(fluxo, confianca, erro), []

    def carregar():
        cargas.append(1)
        if falha_na_carga is not None:
            raise falha_na_carga
        return modelo, lambda textos: None

    return Leitor(carregar, limite), modelo, cargas


@pytest.mark.parametrize(
    "texto",
    ["Não reconheço a cobrança de 45,90 na Streaming Plus", "sim", "2", "roubaram meu cartão"],
)
def test_o_que_as_regras_entendem_nem_chega_ao_leitor(texto):
    ler, modelo, cargas = leitor()
    leitura = ler(texto, "pt", REFERENCIA)
    assert leitura.fonte == "regras" and leitura.chamada is None
    assert modelo.lidos == [] and cargas == []


@pytest.mark.parametrize("texto", ["sí, pásame", "pode passar", "sí, por favor, comunícame"])
def test_aceite_da_oferta_e_das_regras_e_nao_chega_ao_leitor(texto):
    """ACH-125 da validação (EV-155): o aceite largo da oferta (DEV-020t) é das regras. Antes, o
    leitor era chamado e o lia como fora de escopo (0,97 a 0,98), e a conversa não encaminhava."""
    ler, modelo, cargas = leitor(fluxo="fora_de_escopo", confianca=0.98)
    leitura = ler(texto, "es", REFERENCIA)
    assert leitura.fonte == "regras" and leitura.lida.aceita_oferta
    assert modelo.lidos == [] and cargas == []


@pytest.mark.parametrize("texto", ["No, esa no", "Não, essa não"])
def test_recusa_da_transacao_proposta_e_das_regras_e_nao_chega_ao_leitor(texto):
    """ACH-145: "no, esa no" é das regras (a recusa da transação proposta); o leitor a leria como
    outra coisa."""
    ler, modelo, cargas = leitor(fluxo="fora_de_escopo", confianca=0.98)
    leitura = ler(texto, "es", REFERENCIA)
    assert leitura.fonte == "regras" and leitura.lida.outra
    assert modelo.lidos == [] and cargas == []


def test_leitor_confiante_preenche_intencao_e_status_pelo_fluxo():
    ler, modelo, _ = leitor(fluxo="explicar_estorno", confianca=0.93)
    leitura = ler(VAGA, "pt", REFERENCIA)
    assert modelo.lidos == [VAGA]
    assert (leitura.lida.intencao, leitura.lida.status) == ("consultar", "Reversed")
    assert leitura.lida.sinais == ("leitor:explicar_estorno:0.93",)
    assert leitura.fonte == "leitor:e5@abcdef012345"
    assert leitura.chamada.latencia_ms is not None
    assert (leitura.chamada.tokens_entrada, leitura.chamada.tokens_saida) == (0, 0)


def test_abaixo_do_limite_a_mensagem_segue_nao_entendida():
    ler, _, _ = leitor(fluxo="abrir_disputa", confianca=0.79)
    leitura = ler(VAGA, "pt", REFERENCIA)
    assert (leitura.lida.intencao, leitura.lida.status) == ("desconhecida", None)
    assert leitura.fonte == "regras (leitor abaixo do limite)"
    assert leitura.lida.sinais == ("leitor:abrir_disputa:0.79",)


def test_confianca_igual_ao_limite_ja_decide():
    ler, _, _ = leitor(fluxo="relato_de_fraude", confianca=0.8)
    assert ler(VAGA, "pt", REFERENCIA).lida.intencao == "fraude"


def test_carga_que_falha_vira_regras_com_o_motivo_e_nao_e_repetida(caplog):
    ler, _, cargas = leitor(falha_na_carga=FileNotFoundError("sem artefato"))
    with caplog.at_level(logging.WARNING, logger="jeje.leitor"):
        primeira = ler(VAGA, "pt", REFERENCIA)
        segunda = ler("outra coisa estranha", "pt", REFERENCIA)
    assert primeira.fonte == segunda.fonte == "regras (fallback: FileNotFoundError)"
    assert primeira.lida.intencao == "desconhecida"
    assert cargas == [1]
    assert [r.getMessage() for r in caplog.records] == [
        "leitor indisponivel erro=FileNotFoundError"
    ]


def test_falha_ao_ler_vira_regras_e_a_chamada_fica_contada():
    ler, _, _ = leitor(erro=RuntimeError("tensor"))
    leitura = ler(VAGA, "pt", REFERENCIA)
    assert leitura.fonte == "regras (fallback: RuntimeError)"
    assert leitura.lida.intencao == "desconhecida"
    assert leitura.chamada is not None


def test_arquivos_ausentes_viram_regras_sem_carregar_o_e5(tmp_path):
    ler = Leitor(dos_arquivos(tmp_path / "leitor.joblib", tmp_path / "e5"), 0.8)
    assert ler(VAGA, "pt", REFERENCIA).fonte == "regras (fallback: FonteInvalida)"


def com_leitor(settings, tmp_path):
    return settings.model_copy(
        update={
            "interpretador": "leitor",
            "leitor_modelo": tmp_path / "leitor.joblib",
            "leitor_e5": tmp_path / "e5",
            "leitor_limite": 0.7,
        }
    )


def test_api_com_leitor_pede_a_carga_ao_iniciar_e_sobe_mesmo_sem_ele(
    cenario_conversa, tmp_path, caplog
):
    with (
        caplog.at_level(logging.WARNING, logger="jeje.leitor"),
        cliente(com_leitor(cenario_conversa, tmp_path)) as http,
    ):
        http.app.state.carga_do_modelo.join(5)
        viva = http.get("/health")
        configurado = http.app.state.interpretador
    assert viva.status_code == 200
    assert isinstance(configurado, Leitor) and configurado.limite == 0.7
    assert [r.getMessage() for r in caplog.records if r.name == "jeje.leitor"] == [
        "leitor indisponivel erro=FonteInvalida"
    ]
    assert (
        interpretacao_modelo.carregar_em_segundo_plano(interpretacao_modelo.pelas_regras, 1) is None
    )


def test_na_conversa_o_leitor_so_le_e_o_turno_registra_quem_leu(cenario_conversa):
    ler, _, _ = leitor(fluxo="abrir_disputa", confianca=0.95)
    with cliente(cenario_conversa) as http:
        http.app.state.interpretador = ler
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "pt")
        vaga = dizer(http, auth, conversa, VAGA)
    # O leitor entendeu "contestar", mas sem pista a política pergunta qual transação.
    assert (vaga["regra"], vaga["acao"], len(vaga["opcoes"])) == ("POL-CON-02", "esclarecer", 5)
    with conexao(cenario_conversa) as con:
        (evento,) = con.execute(
            text(
                "SELECT interpretacao, modelo_latencia_ms IS NOT NULL, modelo_tokens_entrada"
                " FROM app.eventos WHERE tipo = 'turno'"
            )
        ).all()
    assert tuple(evento) == ("leitor:e5@abcdef012345", True, 0)


def test_no_modo_leitor_o_aceite_comum_da_oferta_encaminha(cenario_conversa):
    """O modo padrão da demo: a oferta do fora de escopo aceita com "sí, pásame" encaminha."""
    ler, _, _ = leitor(fluxo="fora_de_escopo", confianca=0.98)
    with cliente(cenario_conversa) as http:
        http.app.state.interpretador = ler
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        oferta = dizer(http, auth, conversa, "quiero ver mi saldo")
        aceite = dizer(http, auth, conversa, "sí, pásame")
    assert (oferta["acao"], oferta["estado"]) == ("oferecer_humano", "oferecendo_humano")
    assert (aceite["acao"], aceite["estado"]) == ("humano", "com_humano")
