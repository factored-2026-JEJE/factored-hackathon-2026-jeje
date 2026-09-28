"""Conversa sem modelo pela API real (G10): os três caminhos em ES e PT e o que não pode acontecer
— efeito sem confirmação explícita, turno que pula a política, humano respondido pela automação,
dado de outro cliente. O esperado de cada resposta está escrito aqui (texto aprovado + fatos da
fixture), e o efeito é conferido no banco, não só na resposta."""

from concurrent.futures import ThreadPoolExecutor

import httpx2 as httpx
import pytest
from conftest import abrir_conversa, autenticar, cliente, conexao, dizer, servidor_http
from sqlalchemy import text


@pytest.fixture
def cenario(cenario_conversa):
    return cenario_conversa


def contar(settings, tabela: str) -> int:
    with conexao(settings) as con:
        return con.execute(text(f"SELECT count(*) FROM app.{tabela}")).scalar_one()


def pre_casos(settings) -> list[tuple]:
    with conexao(settings) as con:
        consulta = "SELECT protocolo, customer_id, transaction_id FROM app.pre_casos"
        return [tuple(linha) for linha in con.execute(text(consulta))]


def handoffs(settings) -> list[dict]:
    with conexao(settings) as con:
        return [
            dict(linha)
            for linha in con.execute(
                text(
                    "SELECT id, customer_id, regra, idioma, pedido, transacao, acoes, pendencias"
                    " FROM app.handoffs ORDER BY id"
                )
            ).mappings()
        ]


A1 = {
    "es": "en Streaming Plus de USD 45,90 (10/03/2025)",
    "pt": "em Streaming Plus de USD 45,90 (10/03/2025)",
}

# ---- Caminho normal ---------------------------------------------------------------------------

NORMAL = {
    "es": {
        "pedido": "No reconozco el cobro de 45,90 en Streaming Plus",
        "proposta": f"Puedo registrar una solicitud de revisión (pre-caso) de la transacción "
        f"{A1['es']}. Esto no devuelve el dinero ni resuelve la disputa. ¿Confirmas?",
        "sim": "Sí",
        "registrado": "Registré la solicitud con el protocolo {p}. Es un registro para revisión, "
        "no un reembolso.",
    },
    "pt": {
        "pedido": "Não reconheço a cobrança de 45,90 na Streaming Plus",
        "proposta": f"Posso registrar um pedido de revisão (pré-caso) da transação {A1['pt']}. "
        "Isso não devolve o dinheiro nem resolve a contestação. Você confirma?",
        "sim": "Sim",
        "registrado": "Registrei o pedido com o protocolo {p}. É um registro para revisão, "
        "não um reembolso.",
    },
}


@pytest.mark.parametrize("idioma", ["es", "pt"])
def test_caminho_normal_propoe_confirma_e_registra_um_pre_caso_relido(cenario, idioma):
    falas = NORMAL[idioma]
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        proposta = dizer(http, auth, conversa, falas["pedido"])
        assert (proposta["regra"], proposta["acao"], proposta["estado"]) == (
            "POL-DISP-01", "propor_pre_caso", "confirmando"
        )  # fmt: skip
        assert (proposta["idioma"], proposta["transaction_id"]) == (idioma, "TRX-A1")
        assert proposta["resposta"] == falas["proposta"]
        assert pre_casos(cenario) == []  # proposta não é efeito

        registrado = dizer(http, auth, conversa, falas["sim"])
        assert (registrado["regra"], registrado["acao"], registrado["estado"]) == (
            "POL-DISP-01", "registrar_pre_caso", "livre"
        )  # fmt: skip
        protocolo = registrado["protocolo"]
        assert pre_casos(cenario) == [(protocolo, "CLI-A", "TRX-A1")]
        assert registrado["resposta"] == falas["registrado"].format(p=protocolo)

        # Repetir o "sim" não cria nada: não há mais proposta pendente.
        de_novo = dizer(http, auth, conversa, falas["sim"])
        assert de_novo["acao"] != "registrar_pre_caso"
        assert pre_casos(cenario) == [(protocolo, "CLI-A", "TRX-A1")]


CONSULTA = {
    "es": (
        "¿Por qué rechazaron mi compra en Almacenes Éxito?",
        "La transacción en Almacenes Éxito de COP 189.900,55 (12/03/2025) fue rechazada. Motivo "
        "informado en el código 51: fondos insuficientes (significado genérico del estándar ISO "
        "8583).",
    ),
    "pt": (
        "Por que recusaram minha compra no Almacenes Éxito?",
        "A transação em Almacenes Éxito de COP 189.900,55 (12/03/2025) foi recusada. Motivo "
        "informado no código 51: saldo insuficiente (significado genérico do padrão ISO 8583).",
    ),
}


@pytest.mark.parametrize("idioma", ["es", "pt"])
def test_caminho_normal_consulta_de_recusa_explica_o_codigo(cenario, idioma):
    pergunta, esperado = CONSULTA[idioma]
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        resposta = dizer(http, auth, abrir_conversa(http, auth, "es"), pergunta)
    assert (resposta["regra"], resposta["acao"], resposta["transaction_id"]) == (
        "POL-CON-03", "responder", "TRX-A2"
    )  # fmt: skip
    assert resposta["resposta"] == esperado


def test_pendente_informa_o_status_sem_prometer_prazo(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        resposta = dizer(
            http, auth, abrir_conversa(http, auth, "pt"), "a compra no Café Central está pendente?"
        )
    assert (resposta["regra"], resposta["transaction_id"]) == ("POL-CON-05", "TRX-A5")
    assert resposta["resposta"] == (
        "A transação em Café Central de USD 12,00 (16/03/2025) está pendente. Informo o que "
        "consta hoje no registro."
    )


# ---- Caminho ambíguo --------------------------------------------------------------------------

AMBIGUO = {
    "es": (
        "No reconozco un cobro de 45,90",
        "la segunda",
        "Encontré más de una transacción posible. ¿Cuál de estas es?",
    ),
    "pt": (
        "Não reconheço uma cobrança de 45,90",
        "a segunda",
        "Encontrei mais de uma transação possível. Qual destas é?",
    ),
}


@pytest.mark.parametrize("idioma", ["es", "pt"])
def test_caminho_ambiguo_so_age_depois_que_o_cliente_escolhe(cenario, idioma):
    pedido, escolha, cabecalho = AMBIGUO[idioma]
    preposicao = {"es": "en", "pt": "em"}[idioma]
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, idioma)
        pergunta = dizer(http, auth, conversa, pedido)
        assert (pergunta["regra"], pergunta["acao"], pergunta["estado"]) == (
            "POL-CON-02", "esclarecer", "esclarecendo"
        )  # fmt: skip
        # Só transações do próprio cliente, mais recentes primeiro; nada do TRX-B1 idêntico.
        assert pergunta["opcoes"] == [
            {"numero": 1, "transaction_id": "TRX-A6",
             "descricao": f"{preposicao} Cine Premium de USD 45,90 (11/03/2025)"},
            {"numero": 2, "transaction_id": "TRX-A1", "descricao": f"{A1[idioma]}"},
        ]  # fmt: skip
        assert pergunta["resposta"] == (
            f"{cabecalho}\n1. {preposicao} Cine Premium de USD 45,90 (11/03/2025)\n2. {A1[idioma]}"
        )
        assert contar(cenario, "propostas_pre_caso") == 0  # nada escolhido em silêncio

        escolhida = dizer(http, auth, conversa, escolha)
        assert (escolhida["regra"], escolhida["transaction_id"]) == ("POL-DISP-01", "TRX-A1")
        assert pre_casos(cenario) == []


def test_dois_esclarecimentos_sem_sucesso_encaminham_para_humano(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        primeira = dizer(http, auth, conversa, "No reconozco un cobro de 45,90")
        segunda = dizer(http, auth, conversa, "no sé")
        terceira = dizer(http, auth, conversa, "ni idea")
    assert [t["regra"] for t in (primeira, segunda, terceira)] == [
        "POL-CON-02", "POL-CON-02", "POL-HUM-03"
    ]  # fmt: skip
    assert segunda["opcoes"] == primeira["opcoes"]
    assert terceira["acao"] == "humano" and terceira["estado"] == "com_humano"
    [encaminhado] = handoffs(cenario)
    assert (encaminhado["regra"], encaminhado["pedido"]) == (
        "POL-HUM-03", "No reconozco un cobro de 45,90"
    )  # fmt: skip
    assert encaminhado["pendencias"] == [
        "Atender o cliente no pedido abaixo (esclarecimentos sem sucesso)"
    ]


def test_valor_que_nao_casa_pede_dados_sem_inventar_transacao(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        resposta = dizer(
            http, auth, abrir_conversa(http, auth, "pt"), "não reconheço a compra de 999,99"
        )
    assert (resposta["regra"], resposta["opcoes"], resposta["transaction_id"]) == (
        "POL-CON-02", [], None
    )  # fmt: skip
    assert resposta["resposta"] == (
        "Não encontrei essa transação na sua conta. Pode me dizer o valor, a data ou o "
        "estabelecimento?"
    )


# ---- Caminho humano ---------------------------------------------------------------------------

FRAUDE = {
    "es": (
        "Me robaron la tarjeta y hay un cobro que no reconozco",
        "Por seguridad, un agente va a atender este caso. Ya le paso el resumen.\n"
        "Referencia de la atención: {a}.",
        "¿y ahora qué?",
        "Tu caso ya está con un agente (referencia {a}); la conversación sigue con esa persona.",
    ),
    "pt": (
        "Roubaram meu cartão e tem uma cobrança que não reconheço",
        "Por segurança, um atendente vai cuidar deste caso. Já passo o resumo para ele.\n"
        "Referência do atendimento: {a}.",
        "e agora?",
        "Seu caso já está com um atendente (referência {a}); a conversa segue com essa pessoa.",
    ),
}


@pytest.mark.parametrize("idioma", ["es", "pt"])
def test_caminho_humano_fraude_encaminha_e_a_automacao_para(cenario, idioma):
    relato, esperado, depois, aguardando = FRAUDE[idioma]
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        encaminhado = dizer(http, auth, conversa, relato)
        seguinte = dizer(http, auth, conversa, depois)
        sim = dizer(http, auth, conversa, NORMAL[idioma]["sim"])
    atendimento = encaminhado["atendimento"]
    assert (encaminhado["regra"], encaminhado["acao"], encaminhado["estado"]) == (
        "POL-HUM-01", "humano", "com_humano"
    )  # fmt: skip
    assert encaminhado["resposta"] == esperado.format(a=atendimento)
    # Depois do encaminhamento, a automação só lembra quem está com o caso.
    assert (seguinte["acao"], seguinte["atendimento"]) == ("aguardar_humano", atendimento)
    assert seguinte["resposta"] == aguardando.format(a=atendimento)
    assert sim["acao"] == "aguardar_humano"
    [registro] = handoffs(cenario)
    assert (registro["id"], registro["regra"], registro["idioma"], registro["pedido"]) == (
        atendimento, "POL-HUM-01", idioma, relato
    )  # fmt: skip
    assert registro["pendencias"] == [
        "Tratar relato de fraude: bloqueio e análise do cartão (relato de fraude)"
    ]
    assert contar(cenario, "propostas_pre_caso") == 0 and pre_casos(cenario) == []


def test_contestacao_acima_do_limite_encaminha_com_fatos_e_acoes(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        resposta = dizer(
            http, auth, abrir_conversa(http, auth, "es"), "No reconozco la compra en Boutique Moda"
        )
    assert (resposta["regra"], resposta["acao"], resposta["transaction_id"]) == (
        "POL-HUM-02", "humano", "TRX-A4"
    )  # fmt: skip
    [registro] = handoffs(cenario)
    assert registro["transacao"] == {
        "transaction_id": "TRX-A4", "data": "2025-03-15T11:00:00", "valor": "7500.00",
        "moeda": "USD", "comercio": "Boutique Moda", "status": "Approved",
    }  # fmt: skip
    assert registro["acoes"] == [
        {"acao": "identificar_transacao", "resultado": "TRX-A4 (Approved)"},
        {"acao": "avaliar_contestacao", "resultado": "POL-HUM-02: acima do limite simulado"},
    ]
    assert pre_casos(cenario) == [] and contar(cenario, "propostas_pre_caso") == 0


def test_contestacao_noturna_pelo_app_acima_do_limite_vai_para_humano(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        resposta = dizer(
            http, auth, abrir_conversa(http, auth, "es"), "No reconozco la compra en Farmacia Salud"
        )
    assert (resposta["regra"], resposta["acao"], resposta["transaction_id"]) == (
        "POL-HUM-04", "humano", "TRX-A7"
    )  # fmt: skip
    assert resposta["resposta"].startswith(
        "Por seguridad, las solicitudes sobre transacciones hechas de noche por la app o la web "
        "por encima del límite automático las revisa un agente."
    )
    [registro] = handoffs(cenario)
    assert registro["pendencias"] == [
        "Revisar contestação de transação noturna por celular ou computador "
        "(noturna digital acima do limite por transação)"
    ]
    assert pre_casos(cenario) == [] and contar(cenario, "propostas_pre_caso") == 0


def test_mensagens_nao_entendidas_seguidas_encaminham_para_humano(cenario):
    """ACH-029: 'no entendí' também é esclarecimento; o terceiro seguido vai para humano."""
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        respostas = [dizer(http, auth, conversa, m) for m in ("asdf", "zzzz", "???")]
    assert [r["regra"] for r in respostas] == ["AJUDA", "AJUDA", "POL-HUM-03"]
    assert (respostas[2]["acao"], respostas[2]["estado"]) == ("humano", "com_humano")
    [registro] = handoffs(cenario)
    assert (registro["regra"], registro["pedido"]) == ("POL-HUM-03", "asdf")
    assert registro["acoes"] == [
        {"acao": "esclarecer", "resultado": "2 mensagens seguidas não entendidas"}
    ]
    assert registro["pendencias"] == [
        "Atender o cliente no pedido abaixo (esclarecimentos sem sucesso)"
    ]


def test_pedido_entendido_no_meio_zera_a_contagem(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, "asdf")
        consulta = dizer(http, auth, conversa, "¿Por qué rechazaron mi compra en Almacenes Éxito?")
        depois = [dizer(http, auth, conversa, m) for m in ("zzzz", "???")]
    assert consulta["regra"] == "POL-CON-03"
    assert [r["regra"] for r in depois] == ["AJUDA", "AJUDA"]
    assert handoffs(cenario) == []


def test_contestacao_de_recusada_explica_e_encaminha_sem_pre_caso(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        resposta = dizer(
            http,
            auth,
            abrir_conversa(http, auth, "pt"),
            "Não reconheço a compra no Almacenes Éxito",
        )
    assert (resposta["regra"], resposta["acao"], resposta["transaction_id"]) == (
        "POL-DISP-02", "humano", "TRX-A2"
    )  # fmt: skip
    assert resposta["resposta"].startswith(
        "A transação em Almacenes Éxito de COP 189.900,55 (12/03/2025) está recusada e não "
        "pode ser contestada automaticamente."
    )
    assert [h["regra"] for h in handoffs(cenario)] == ["POL-DISP-02"]
    assert pre_casos(cenario) == []


def test_recusa_sem_motivo_oferece_atendente_e_so_encaminha_com_sim(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        oferta = dizer(http, auth, conversa, "¿Por qué rechazaron lo de Uber?")
        recusada = dizer(http, auth, conversa, "no, gracias")
        assert handoffs(cenario) == []
        dizer(http, auth, conversa, "¿Por qué rechazaron lo de Uber?")
        aceita = dizer(http, auth, conversa, "sí")
    assert (oferta["regra"], oferta["estado"]) == ("POL-CON-04", "oferecendo_humano")
    assert oferta["resposta"] == (
        "La transacción en Uber de USD 20,00 (14/03/2025) fue rechazada y no tenemos el motivo "
        "registrado. Si quieres, te comunico con un agente."
    )
    assert (recusada["regra"], recusada["estado"]) == ("CANCELADO", "livre")
    assert (aceita["regra"], aceita["acao"], aceita["transaction_id"]) == (
        "POL-HUM-03", "humano", "TRX-A3"
    )  # fmt: skip
    [registro] = handoffs(cenario)
    assert registro["transacao"]["transaction_id"] == "TRX-A3"
    assert {"acao": "consultar_situacao", "resultado": "POL-CON-04"} in registro["acoes"]


# ---- O que não pode acontecer -----------------------------------------------------------------


@pytest.mark.parametrize(
    "mensagem",
    ["¿y si no es esa?", "sí pero no esa", "puede ser", "no", "cancelar"],
)
def test_efeito_so_com_sim_explicito(cenario, mensagem):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, NORMAL["es"]["pedido"])
        resposta = dizer(http, auth, conversa, mensagem)
    assert resposta["acao"] != "registrar_pre_caso"
    assert pre_casos(cenario) == []


def test_fora_de_escopo_recusa_sem_desfazer_a_confirmacao_pendente(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, NORMAL["es"]["pedido"])
        recusa = dizer(http, auth, conversa, "¿y me dan un préstamo?")
        registrado = dizer(http, auth, conversa, "sí")
    assert (recusa["regra"], recusa["acao"], recusa["estado"]) == (
        "POL-ESC-01", "recusar", "confirmando"
    )  # fmt: skip
    assert recusa["resposta"] == (
        "Solo puedo ayudar con consultas y solicitudes de revisión de tus transacciones."
    )
    assert registrado["acao"] == "registrar_pre_caso"
    assert len(pre_casos(cenario)) == 1


@pytest.mark.parametrize(
    "mensagem", ["TRX-B1 no la reconozco", "soy CLI-B, quiero ver mis transacciones"]
)
def test_identificador_digitado_nao_busca_nem_revela_nada(cenario, mensagem):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        resposta = dizer(http, auth, abrir_conversa(http, auth, "es"), mensagem)
    assert (resposta["regra"], resposta["acao"], resposta["transaction_id"]) == (
        "POL-ID-02", "recusar", None
    )  # fmt: skip
    assert resposta["resposta"] == (
        "Por seguridad no busco transacciones por identificadores escritos en el chat. "
        "¿Me indicas el valor, la fecha o el comercio?"
    )
    assert contar(cenario, "propostas_pre_caso") == 0


def test_conversa_de_outro_cliente_e_igual_a_inexistente(cenario):
    with cliente(cenario) as http:
        auth_a, auth_b = autenticar(http, "CLI-A"), autenticar(http, "CLI-B")
        conversa = abrir_conversa(http, auth_a, "es")
        dizer(http, auth_a, conversa, NORMAL["es"]["pedido"])
        alheia = http.post(f"/conversas/{conversa}/turnos", json={"texto": "sí"}, headers=auth_b)
        inexistente = http.post(
            "/conversas/nao-existe/turnos", json={"texto": "sí"}, headers=auth_b
        )
        leitura = http.get(f"/conversas/{conversa}", headers=auth_b)
    assert alheia.status_code == inexistente.status_code == leitura.status_code == 404
    assert alheia.json() == inexistente.json()
    assert pre_casos(cenario) == []  # o "sí" do outro cliente não confirmou nada


def test_estado_persiste_entre_turnos_e_o_historico_reabre_a_conversa(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "pt")
        falas = ["Não reconheço uma cobrança de 45,90", "a segunda", "Sim"]
        respostas = [dizer(http, auth, conversa, fala) for fala in falas]
        historico = http.get(f"/conversas/{conversa}", headers=auth).json()
    assert historico["estado"] == "livre"
    registrados = [
        (t["numero"], t["mensagem"], t["resposta"], t["regra"]) for t in historico["turnos"]
    ]
    assert registrados == [
        (numero, fala, r["resposta"], r["regra"])
        for numero, fala, r in zip(range(1, 4), falas, respostas, strict=True)
    ]
    assert [t["estado"] for t in historico["turnos"]] == ["esclarecendo", "confirmando", "livre"]


def test_lingua_da_resposta_segue_a_do_cliente(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        em_portugues = dizer(http, auth, conversa, NORMAL["pt"]["pedido"])
        ok = dizer(http, auth, conversa, "ok")
    assert em_portugues["idioma"] == "pt" and em_portugues["resposta"] == NORMAL["pt"]["proposta"]
    assert ok["idioma"] == "pt"  # empate mantém a língua anterior


@pytest.mark.parametrize("texto_enviado", ["", "x" * 501])
def test_mensagem_vazia_ou_longa_demais_e_recusada_na_borda(cenario, texto_enviado):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        resposta = http.post(
            f"/conversas/{conversa}/turnos", json={"texto": texto_enviado}, headers=auth
        )
    assert resposta.status_code == 422
    assert contar(cenario, "turnos") == 0


def test_falha_ao_gravar_desfaz_o_turno_e_o_reenvio_registra_um(cenario):
    with conexao(cenario) as con:
        con.execute(
            text(
                "CREATE FUNCTION app.falhar() RETURNS trigger LANGUAGE plpgsql AS"
                " $$ BEGIN RAISE EXCEPTION 'disco cheio (simulado)'; END $$;"
                " CREATE TRIGGER falhar BEFORE INSERT ON app.pre_casos"
                " FOR EACH ROW EXECUTE FUNCTION app.falhar()"
            )
        )
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, NORMAL["es"]["pedido"])
        falhou = http.post(f"/conversas/{conversa}/turnos", json={"texto": "sí"}, headers=auth)
        assert falhou.status_code == 503
        assert "nada foi criado" in falhou.json()["detail"]
        assert pre_casos(cenario) == []
        with conexao(cenario) as con:
            estado, turnos = con.execute(
                text("SELECT estado, turnos FROM app.conversas WHERE id = :id"), {"id": conversa}
            ).one()
            con.execute(text("DROP TRIGGER falhar ON app.pre_casos"))
        assert (estado, turnos) == ("confirmando", 1)  # o turno inteiro foi desfeito
        registrado = dizer(http, auth, conversa, "sí")
    assert registrado["numero"] == 2 and registrado["acao"] == "registrar_pre_caso"
    assert len(pre_casos(cenario)) == 1


def test_turnos_simultaneos_na_mesma_conversa_sao_serializados(cenario):
    with servidor_http(cenario) as url, httpx.Client(base_url=url) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")

        def enviar(_):
            return http.post(f"/conversas/{conversa}/turnos", json={"texto": "hola"}, headers=auth)

        with ThreadPoolExecutor(max_workers=6) as grupo:
            respostas = list(grupo.map(enviar, range(6)))
    assert [r.status_code for r in respostas] == [200] * 6
    assert sorted(r.json()["numero"] for r in respostas) == [1, 2, 3, 4, 5, 6]
