"""Bloqueio de cartão na conversa (PRD-007), pela API real: o pedido e o relato de fraude bloqueiam
pelo dispositivo da sessão (nunca pelo chat), com vários cartões pergunta qual, a fraude sempre
chega ao atendente e o desbloqueio fica com ele — sempre conferindo o banco, não só a resposta."""

import json

import pytest
from conftest import (
    abrir_conversa,
    cliente,
    conexao,
    curar_tudo,
    dizer,
    raw_transacao,
)
from sqlalchemy import text

from jeje import sessao


@pytest.fixture
def cenario(cartoes):
    """Os donos dos cartões viram personas: CLI-A (crédito 9241 e débito 5678 ativos, um crédito
    fechado), CLI-B (crédito 1111) e CLI-C (só um débito já bloqueado na base)."""
    with conexao(cartoes) as con:
        raw_transacao(con, "TRX-A1", "CLI-A", "PRD-A")
        raw_transacao(con, "TRX-B1", "CLI-B", "PRD-B")
        raw_transacao(con, "TRX-C1", "CLI-C", "CRT-C1")
    curar_tudo(cartoes)
    with conexao(cartoes) as con:
        sessao.provisionar_personas(con, 3)
    return cartoes


def entrar(http, cliente_id: str, dispositivo: str | None = None) -> dict:
    corpo = {"customer_id": cliente_id} | ({"dispositivo": dispositivo} if dispositivo else {})
    token = http.post("/sessoes", json=corpo).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def bloqueios(settings) -> list[dict]:
    with conexao(settings) as con:
        linhas = con.execute(
            text(
                "SELECT id, customer_id, product_id, tipo, motivo, dispositivo, desfeito_em,"
                " atendimento FROM app.bloqueios ORDER BY id"
            )
        ).mappings()
        return [dict(linha) for linha in linhas]


def handoffs(settings) -> list[dict]:
    with conexao(settings) as con:
        linhas = con.execute(
            text("SELECT id, regra, pedido, acoes, pendencias FROM app.handoffs ORDER BY id")
        ).mappings()
        return [dict(linha) for linha in linhas]


def acoes_de_bloqueio(settings) -> list[tuple]:
    """Eventos `acao` de bloqueio (o bloqueio feito num turno que encaminha)."""
    with conexao(settings) as con:
        return [
            tuple(linha)
            for linha in con.execute(
                text(
                    "SELECT regra, efeito, fontes FROM app.eventos"
                    " WHERE tipo = 'acao' AND acao = 'bloquear_cartao' ORDER BY id"
                )
            )
        ]


def test_pedido_com_dispositivo_cadastrado_bloqueia_por_completo_sem_encaminhar(cenario):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", "cadastrado")
        turno = dizer(http, auth, abrir_conversa(http, auth, "es"), "quiero bloquear mi tarjeta")
        console = http.get("/atendimento/bloqueios").json()
    [feito] = bloqueios(cenario)
    assert (turno["regra"], turno["acao"], turno["estado"]) == (
        "POL-BLQ-02", "bloquear_cartao", "livre"
    )  # fmt: skip
    assert (turno["bloqueio"], turno["atendimento"]) == (feito["id"], None)
    assert turno["resposta"] == (
        f"Bloqueé tu tarjeta de crédito terminada en 1111 (bloqueo completo simulado, referencia"
        f" {feito['id']}).\nSi fue un error, pídeme deshacerlo."
    )
    assert (feito["customer_id"], feito["product_id"], feito["tipo"], feito["motivo"]) == (
        "CLI-B", "CRT-B1", "completo", "pedido"
    )  # fmt: skip
    assert (feito["dispositivo"], feito["atendimento"]) == ("cadastrado", None)
    # O aviso ao atendente é o bloqueio no console; ninguém é encaminhado.
    assert [b["id"] for b in console] == [feito["id"]]
    assert handoffs(cenario) == []
    # O turno é o próprio bloqueio (efeito do turno): nenhum evento `acao` a mais.
    with conexao(cenario) as con:
        consulta = "SELECT acao, efeito FROM app.eventos WHERE tipo = 'turno'"
        assert [tuple(e) for e in con.execute(text(consulta))] == [("bloquear_cartao", feito["id"])]
    assert acoes_de_bloqueio(cenario) == []


@pytest.mark.parametrize(
    ("idioma", "pergunta", "sim"),
    [
        ("es", "¿Cómo bloqueo la tarjeta si la pierdo?", "Sí"),
        ("pt", "Dá para bloquear o cartão pelo chat?", "Sim"),
    ],
)
def test_pergunta_hipotetica_confirma_e_o_sim_bloqueia(cenario, idioma, pergunta, sim):
    """REG-20: a pergunta não bloqueia na hora; espera o sim (POL-BLQ-07) e então bloqueia."""
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", "cadastrado")
        conversa = abrir_conversa(http, auth, idioma)
        confirma = dizer(http, auth, conversa, pergunta)
        antes = bloqueios(cenario)
        feito = dizer(http, auth, conversa, sim)
    assert (confirma["regra"], confirma["acao"], confirma["estado"]) == (
        "POL-BLQ-07", "esclarecer", "confirmando_bloqueio"
    )  # fmt: skip
    assert antes == []
    assert (feito["regra"], feito["acao"], feito["estado"]) == (
        "POL-BLQ-02", "bloquear_cartao", "livre"
    )  # fmt: skip
    assert [b["product_id"] for b in bloqueios(cenario)] == ["CRT-B1"]


def test_pergunta_hipotetica_com_nao_nao_bloqueia(cenario):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, "¿Cómo bloqueo la tarjeta si la pierdo?")
        nao = dizer(http, auth, conversa, "No")
    assert (nao["regra"], nao["acao"], nao["estado"]) == ("CANCELADO", "responder", "livre")
    assert nao["resposta"] == "Listo, no bloqueé ninguna tarjeta. ¿Te ayudo con algo más?"
    assert bloqueios(cenario) == []


def test_pedido_com_dispositivo_novo_bloqueia_preventivo_e_encaminha(cenario):
    """Sem escolha no acesso vale "novo"; o que a mensagem diz do aparelho não muda nada."""
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B")
        conversa = abrir_conversa(http, auth, "pt")
        turno = dizer(http, auth, conversa, "estou no meu celular de sempre, bloqueia meu cartão")
    [feito] = bloqueios(cenario)
    assert (turno["regra"], turno["acao"], turno["estado"]) == (
        "POL-BLQ-01", "humano", "com_humano"
    )  # fmt: skip
    assert (feito["tipo"], feito["dispositivo"], turno["bloqueio"]) == (
        "preventivo", "novo", feito["id"]
    )  # fmt: skip
    assert turno["resposta"] == (
        f"Bloqueei o seu cartão de crédito final 1111 (bloqueio preventivo simulado, referência"
        f" {feito['id']}).\nComo o acesso é de um dispositivo novo, um atendente vai confirmar ou"
        f" desfazer o bloqueio. Já passo o resumo para ele.\nReferência do atendimento:"
        f" {turno['atendimento']}."
    )
    [registro] = handoffs(cenario)
    assert (registro["id"], registro["regra"]) == (turno["atendimento"], "POL-BLQ-01")
    assert feito["atendimento"] == registro["id"]  # o caso fica sabendo se o bloqueio for desfeito
    assert registro["pendencias"] == [
        "Confirmar ou desfazer o bloqueio preventivo do cartão (dispositivo novo)"
    ]
    assert {"acao": "bloquear_cartao",
            "resultado": f"{feito['id']}: bloqueio preventivo do cartão de crédito final 1111"
            } in registro["acoes"]  # fmt: skip
    assert acoes_de_bloqueio(cenario) == [
        ("POL-BLQ-01", feito["id"], ["curated.products", "app.bloqueios"])
    ]


@pytest.mark.parametrize(
    ("resposta", "cartao"),
    [
        ("2", "CRT-A2"),
        ("la terminada en 9241", "CRT-A1"),
        ("9241", "CRT-A1"),  # o final, lido só nesta etapa, não vira valor de transação
        ("la de débito", "CRT-A2"),
    ],
)
def test_varios_cartoes_pergunta_qual_e_bloqueia_o_escolhido(cenario, resposta, cartao):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-A", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        pergunta = dizer(http, auth, conversa, "quiero bloquear mi tarjeta")
        antes = bloqueios(cenario)
        escolhido = dizer(http, auth, conversa, resposta)
    assert (pergunta["regra"], pergunta["acao"], pergunta["estado"]) == (
        "POL-BLQ-06", "esclarecer", "escolhendo_cartao"
    )  # fmt: skip
    # O cartão fechado na base não é opção.
    assert pergunta["resposta"] == (
        "¿Cuál tarjeta quieres bloquear?\n1. tarjeta de crédito terminada en 9241\n"
        "2. tarjeta de débito terminada en 5678\nResponde con el número de la opción o con los 4"
        " últimos dígitos."
    )
    assert antes == []
    assert (escolhido["regra"], escolhido["acao"], escolhido["estado"]) == (
        "POL-BLQ-02", "bloquear_cartao", "livre"
    )  # fmt: skip
    assert [(b["product_id"], b["id"]) for b in bloqueios(cenario)] == [
        (cartao, escolhido["bloqueio"])
    ]


def test_final_citado_no_pedido_bloqueia_sem_perguntar(cenario):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-A", "cadastrado")
        turno = dizer(
            http, auth, abrir_conversa(http, auth, "es"), "bloqueen la tarjeta terminada en 5678"
        )
    assert (turno["regra"], turno["acao"]) == ("POL-BLQ-02", "bloquear_cartao")
    assert [b["product_id"] for b in bloqueios(cenario)] == ["CRT-A2"]


def test_sem_cartao_ativo_so_informa_e_cita_os_ja_bloqueados_por_aqui(cenario):
    with cliente(cenario) as http:
        sem_ativo = entrar(http, "CLI-C", "cadastrado")
        nada = dizer(http, sem_ativo, abrir_conversa(http, sem_ativo, "es"), "bloquear mi tarjeta")
        auth = entrar(http, "CLI-B", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        feito = dizer(http, auth, conversa, "quiero bloquear mi tarjeta")
        de_novo = dizer(http, auth, conversa, "quiero bloquear mi tarjeta")
    assert (nada["regra"], nada["acao"], nada["estado"]) == ("POL-BLQ-03", "responder", "livre")
    assert nada["resposta"] == "No encontré ninguna tarjeta activa para bloquear en tu cuenta."
    assert (de_novo["regra"], de_novo["bloqueio"]) == ("POL-BLQ-03", None)
    assert de_novo["resposta"] == (
        "No encontré ninguna tarjeta activa para bloquear en tu cuenta.\nTarjetas ya bloqueadas"
        f" por aquí: tarjeta de crédito terminada en 1111, {feito['bloqueio']}."
    )
    assert len(bloqueios(cenario)) == 1


@pytest.mark.parametrize(
    ("dispositivo", "tipo"), [("cadastrado", "completo"), ("novo", "preventivo")]
)
def test_relato_de_fraude_bloqueia_pelo_dispositivo_e_encaminha(cenario, dispositivo, tipo):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", dispositivo)
        turno = dizer(http, auth, abrir_conversa(http, auth, "es"), "me robaron la tarjeta")
    [feito] = bloqueios(cenario)
    assert (turno["regra"], turno["acao"], turno["estado"]) == (
        "POL-HUM-01", "humano", "com_humano"
    )  # fmt: skip
    assert (feito["tipo"], feito["motivo"], turno["bloqueio"]) == (tipo, "roubo_perda", feito["id"])
    assert turno["resposta"] == (
        f"Bloqueé tu tarjeta de crédito terminada en 1111 (bloqueo {tipo} simulado, referencia"
        f" {feito['id']}).\nPor seguridad, un agente va a atender este caso. Ya le paso el"
        f" resumen.\nReferencia de la atención: {turno['atendimento']}."
    )
    [registro] = handoffs(cenario)
    assert (registro["regra"], registro["pedido"]) == ("POL-HUM-01", "me robaron la tarjeta")
    assert feito["atendimento"] == registro["id"]
    assert {"acao": "bloquear_cartao",
            "resultado": f"{feito['id']}: bloqueio {tipo} do cartão de crédito final 1111"
            } in registro["acoes"]  # fmt: skip
    assert acoes_de_bloqueio(cenario) == [
        ("POL-HUM-01", feito["id"], ["curated.products", "app.bloqueios"])
    ]


def test_a_compra_fraudulenta_depois_do_bloqueio_vai_ao_atendente(cenario):
    """ACH-160 (o portão de 128 do NOV-13a no congelado): o cliente bloqueia o cartão e, no turno
    seguinte, pede a contestação da "compra fraudulenta". É relato de fraude, e a conversa encaminha
    ao atendente, em vez de só perguntar qual transação."""
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", "cadastrado")
        conversa = abrir_conversa(http, auth, "pt")
        pedido = "Me bloqueiem o cartão imediatamente e não quero falar com mais ninguém."
        bloqueio = dizer(http, auth, conversa, pedido)
        relato = dizer(
            http,
            auth,
            conversa,
            "Já está feito e não quero discutir mais isso. Só preciso da contestação da compra"
            " fraudulenta também.",
        )
    assert bloqueio["bloqueio"] is not None
    assert (relato["regra"], relato["acao"], relato["estado"]) == (
        "POL-HUM-01", "humano", "com_humano"
    )  # fmt: skip
    [registro] = handoffs(cenario)
    assert registro["regra"] == "POL-HUM-01"


def test_quem_pergunta_como_evitar_fraude_vai_ao_atendente_sem_bloquear(cenario):
    """ACH-144 (P3 do NOV-35): a pergunta de prevenção lida como fraude vai ao atendente pela
    POL-HUM-01, mas não bloqueia o cartão; o relato de vítima continua bloqueando."""
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", "cadastrado")
        pergunta = "¿Cómo puedo evitar caer en un fraude con la tarjeta?"
        turno = dizer(http, auth, abrir_conversa(http, auth, "es"), pergunta)
    assert (turno["regra"], turno["acao"], turno["estado"]) == (
        "POL-HUM-01", "humano", "com_humano"
    )  # fmt: skip
    assert (turno["bloqueio"], bloqueios(cenario)) == (None, [])
    [registro] = handoffs(cenario)
    assert (registro["regra"], registro["pedido"]) == ("POL-HUM-01", pergunta)


CARTAO_DE_A = {
    "CRT-A1": ("tarjeta de crédito terminada en 9241", "cartão de crédito final 9241"),
    "CRT-A2": ("tarjeta de débito terminada en 5678", "cartão de débito final 5678"),
}


@pytest.mark.parametrize(
    ("resposta", "dispositivo", "bloqueado", "tipo"),
    [
        ("1", "cadastrado", "CRT-A1", "completo"),
        ("la de débito", "novo", "CRT-A2", "preventivo"),
        ("no sé cuál fue", "cadastrado", None, None),
        ("¿por qué rechazaron mi compra?", "cadastrado", None, None),
    ],
)
def test_fraude_com_varios_cartoes_encaminha_ja_e_bloqueia_depois(
    cenario, resposta, dispositivo, bloqueado, tipo
):
    """PRD-009: o caso vai ao atendente no relato, antes de saber o cartão. A resposta, uma vez
    só, bloqueia o escolhido e anota no mesmo caso; sem cartão identificado, nada é bloqueado. Nos
    dois, a conversa fica com o atendente e nenhum outro caso é aberto."""
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-A", dispositivo)
        conversa = abrir_conversa(http, auth, "es")
        pergunta = dizer(http, auth, conversa, "me clonaron una tarjeta")
        [caso] = handoffs(cenario)
        antes = bloqueios(cenario)
        seguinte = dizer(http, auth, conversa, resposta)
        reaberta = http.get(f"/conversas/{conversa}", headers=auth).json()
    atendimento = pergunta["atendimento"]
    assert (pergunta["regra"], pergunta["acao"], pergunta["estado"]) == (
        "POL-HUM-01", "humano", "escolhendo_cartao"
    )  # fmt: skip
    assert (caso["id"], caso["regra"], caso["pedido"]) == (
        atendimento, "POL-HUM-01", "me clonaron una tarjeta"
    )  # fmt: skip
    assert antes == []
    assert pergunta["resposta"] == (
        "Por seguridad, un agente va a atender este caso. Ya le paso el resumen.\n"
        f"Referencia de la atención: {atendimento}.\n"
        "Mientras tanto, puedo bloquear ahora la tarjeta afectada. ¿Cuál es?\n"
        "1. tarjeta de crédito terminada en 9241\n2. tarjeta de débito terminada en 5678\n"
        "Responde con el número de la opción o con los 4 últimos dígitos."
    )
    assert (seguinte["regra"], seguinte["estado"], seguinte["atendimento"]) == (
        "POL-HUM-01", "com_humano", atendimento
    )  # fmt: skip
    lembrete = (
        f"Tu caso ya está con un agente (referencia {atendimento}); la conversación sigue con"
        " esa persona."
    )
    [registro] = handoffs(cenario)
    if bloqueado is None:
        assert (seguinte["acao"], seguinte["bloqueio"]) == ("aguardar_humano", None)
        assert seguinte["resposta"] == (
            f"No identifiqué cuál tarjeta, así que no bloqueé ninguna.\n{lembrete}"
        )
        assert bloqueios(cenario) == []
        feito = "cartão não identificado na resposta; nada bloqueado"
    else:
        [novo] = bloqueios(cenario)
        assert (novo["product_id"], novo["tipo"], novo["motivo"]) == (
            bloqueado,
            tipo,
            "roubo_perda",
        )
        assert novo["atendimento"] == atendimento
        assert (seguinte["acao"], seguinte["bloqueio"], seguinte["efeito"]) == (
            "bloquear_cartao", novo["id"], novo["id"]
        )  # fmt: skip
        dito, resumo = CARTAO_DE_A[bloqueado]
        assert seguinte["resposta"] == (
            f"Bloqueé tu {dito} (bloqueo {tipo} simulado, referencia {novo['id']}).\n{lembrete}"
        )
        feito = f"{novo['id']}: bloqueio {tipo} do {resumo}"
    # O caso guarda o que já tinha (a leitura do relato) e ganha o que a resposta fez.
    assert [a["acao"] for a in registro["acoes"]] == ["interpretar", "bloquear_cartao"]
    assert registro["acoes"][-1] == {"acao": "bloquear_cartao", "resultado": feito}
    assert reaberta["atendimento"] == atendimento
    assert acoes_de_bloqueio(cenario) == []  # o bloqueio é o efeito do próprio turno


@pytest.mark.parametrize("mensagem", ["quiero hablar con un agente", "me robaron otra tarjeta"])
def test_na_escolha_do_cartao_da_fraude_nada_abre_outro_caso(cenario, mensagem):
    """Com o caso já no atendente, qualquer mensagem é a resposta à pergunta do cartão, inclusive
    um novo relato ou um pedido de atendente."""
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-A", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        atendimento = dizer(http, auth, conversa, "me clonaron una tarjeta")["atendimento"]
        seguinte = dizer(http, auth, conversa, mensagem)
    assert (seguinte["estado"], seguinte["atendimento"]) == ("com_humano", atendimento)
    assert [h["id"] for h in handoffs(cenario)] == [atendimento]
    assert bloqueios(cenario) == []


def test_conversa_que_esperava_o_cartao_da_fraude_sem_caso_aberto_encaminha_na_resposta(cenario):
    """Conversa parada na pergunta de antes do PRD-009, que perguntava antes de encaminhar: a
    resposta abre o caso, com o que já tinha sido feito, e bloqueia o escolhido."""
    legado = {
        "cartoes": ["CRT-A1", "CRT-A2"],
        "motivo": "roubo_perda",
        "pedido": "me clonaron una tarjeta",
        "perguntas": 1,
        "acoes": [{"acao": "interpretar", "resultado": "POL-HUM-01: fraude"}],
    }
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-A", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        with conexao(cenario) as con:
            con.execute(
                text(
                    "UPDATE app.conversas SET estado = 'escolhendo_cartao',"
                    " contexto = CAST(:contexto AS jsonb) WHERE id = :id"
                ),
                {"contexto": json.dumps(legado), "id": conversa},
            )
        turno = dizer(http, auth, conversa, "1")
    [registro] = handoffs(cenario)
    [novo] = bloqueios(cenario)
    assert (turno["estado"], turno["atendimento"], turno["bloqueio"]) == (
        "com_humano", registro["id"], novo["id"]
    )  # fmt: skip
    assert (registro["regra"], registro["pedido"]) == ("POL-HUM-01", "me clonaron una tarjeta")
    assert [a["acao"] for a in registro["acoes"]] == ["interpretar", "bloquear_cartao"]
    assert novo["product_id"] == "CRT-A1"


@pytest.mark.parametrize("mensagem", ["1", "no sé cuál fue"])
def test_caso_que_sumiu_antes_da_resposta_desfaz_o_turno_sem_bloquear(cenario, mensagem):
    """Sem o caso, nada é anotado nem bloqueado: o turno inteiro é desfeito (503). Com o cartão
    escolhido, a ligação do bloqueio ao caso também falha; sem ele, só a anotação confere."""
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-A", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, "me clonaron una tarjeta")
        with conexao(cenario) as con:
            con.execute(text("DELETE FROM app.handoffs"))
        resposta = http.post(
            f"/conversas/{conversa}/turnos", json={"texto": mensagem}, headers=auth
        )
    assert resposta.status_code == 503
    assert "nada foi criado" in resposta.json()["detail"]
    assert bloqueios(cenario) == []


def test_fraude_sem_cartao_ativo_so_encaminha(cenario):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-C", "cadastrado")
        turno = dizer(http, auth, abrir_conversa(http, auth, "pt"), "roubaram meu cartão")
    assert (turno["regra"], turno["acao"], turno["estado"], turno["bloqueio"]) == (
        "POL-HUM-01", "humano", "com_humano", None
    )  # fmt: skip
    assert turno["resposta"].startswith("Por segurança, um atendente vai cuidar deste caso.")
    assert bloqueios(cenario) == []


def test_desbloqueio_sem_bloqueio_feito_por_aqui_vai_para_o_atendente(cenario):
    """O cartão de CLI-C foi bloqueado pelo banco, não pela conversa: quem desfaz é o atendente."""
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-C", "cadastrado")
        turno = dizer(http, auth, abrir_conversa(http, auth, "es"), "quiero desbloquear mi tarjeta")
    assert (turno["regra"], turno["acao"], turno["estado"]) == (
        "POL-BLQ-05", "humano", "com_humano"
    )  # fmt: skip
    assert turno["resposta"].startswith(
        "Para deshacer un bloqueo, un agente revisa la solicitud. Ya le paso el resumen."
    )
    [registro] = handoffs(cenario)
    assert registro["pendencias"] == [
        "Revisar pedido de desbloqueio de cartão (sem bloqueio feito por aqui)"
    ]


def desfeitos(settings) -> list[tuple]:
    with conexao(settings) as con:
        consulta = "SELECT id, desfeito_por FROM app.bloqueios WHERE desfeito_em IS NOT NULL"
        return [tuple(linha) for linha in con.execute(text(consulta))]


def test_cliente_desfaz_pela_conversa_o_bloqueio_que_pediu_dentro_do_prazo(cenario):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        feito = dizer(http, auth, conversa, "quiero bloquear mi tarjeta")["bloqueio"]
        proposta = dizer(http, auth, conversa, "quiero desbloquear mi tarjeta")
        antes = desfeitos(cenario)
        desfeito = dizer(http, auth, conversa, "Sí, confirmo")
        console = http.get("/atendimento/bloqueios").json()
    assert (proposta["regra"], proposta["acao"], proposta["estado"]) == (
        "POL-BLQ-04", "propor_desbloqueio", "confirmando_desbloqueio"
    )  # fmt: skip
    assert proposta["resposta"] == (
        "¿Confirmas que quieres deshacer el bloqueo de tu tarjeta de crédito terminada en 1111"
        f" (referencia {feito})? Responde sí o no."
    )
    assert antes == []  # nada desfeito sem o sim
    assert (desfeito["regra"], desfeito["acao"], desfeito["estado"]) == (
        "POL-BLQ-04", "desbloquear_cartao", "livre"
    )  # fmt: skip
    assert (desfeito["bloqueio"], desfeito["efeito"]) == (feito, feito)
    assert desfeito["resposta"] == (
        "Listo: deshice el bloqueo de tu tarjeta de crédito terminada en 1111"
        f" (referencia {feito})."
    )
    assert desfeitos(cenario) == [(feito, "cliente")]
    assert console == []
    assert handoffs(cenario) == []


@pytest.mark.parametrize("mensagem", ["sí, adelante", "pode passar", "beleza", "por favor"])
def test_aceite_largo_da_oferta_nao_desfaz_o_bloqueio(cenario, mensagem):
    """ACH-123: o aceite largo vale só para a oferta do atendente; desbloquear pede o sim
    estrito."""
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, "quiero bloquear mi tarjeta")
        dizer(http, auth, conversa, "quiero desbloquear mi tarjeta")
        dizer(http, auth, conversa, mensagem)
    assert desfeitos(cenario) == []


def test_nao_ao_desbloqueio_mantem_o_bloqueio(cenario):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", "cadastrado")
        conversa = abrir_conversa(http, auth, "pt")
        dizer(http, auth, conversa, "quero bloquear meu cartão")
        dizer(http, auth, conversa, "quero desbloquear meu cartão")
        mantido = dizer(http, auth, conversa, "não")
    assert (mantido["regra"], mantido["estado"]) == ("CANCELADO", "livre")
    assert mantido["resposta"] == (
        "Tudo bem, o bloqueio continua. Posso ajudar com mais alguma coisa?"
    )
    assert desfeitos(cenario) == []


@pytest.mark.parametrize("bloquear", ["quiero bloquear mi tarjeta", "me robaron la tarjeta"])
def test_bloqueio_fora_do_prazo_so_o_atendente_desfaz(cenario, bloquear):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", "cadastrado")
        dizer(http, auth, abrir_conversa(http, auth, "es"), bloquear)
        with conexao(cenario) as con:
            con.execute(
                text("UPDATE app.bloqueios SET reversivel_ate = now() - interval '1 second'")
            )
        turno = dizer(http, auth, abrir_conversa(http, auth, "es"), "quiero desbloquear mi tarjeta")
    assert (turno["regra"], turno["acao"], turno["estado"]) == (
        "POL-BLQ-05", "humano", "com_humano"
    )  # fmt: skip
    assert handoffs(cenario)[-1]["pendencias"] == [
        "Revisar pedido de desbloqueio de cartão (fora do prazo de reversão)"
    ]
    assert desfeitos(cenario) == []


def test_cliente_desfaz_em_ate_7_dias_o_bloqueio_do_relato_de_roubo_e_o_caso_fica_sabendo(cenario):
    """PRD-009: em caso de urgência, o cliente desfaz pela conversa, com um sim e dentro do prazo, o
    bloqueio que veio do relato de roubo; o caso do atendente ganha a ação."""
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", "cadastrado")
        relato = dizer(http, auth, abrir_conversa(http, auth, "es"), "me robaron la tarjeta")
        console = http.get("/atendimento/bloqueios").json()
        conversa = abrir_conversa(http, auth, "es")
        proposta = dizer(http, auth, conversa, "quiero desbloquear mi tarjeta")
        desfeito = dizer(http, auth, conversa, "sí")
    feito, atendimento = relato["bloqueio"], relato["atendimento"]
    assert [(b["id"], b["atendimento"]) for b in console] == [(feito, atendimento)]
    assert (proposta["regra"], proposta["estado"]) == ("POL-BLQ-04", "confirmando_desbloqueio")
    assert (desfeito["regra"], desfeito["acao"], desfeito["bloqueio"]) == (
        "POL-BLQ-04", "desbloquear_cartao", feito
    )  # fmt: skip
    assert desfeitos(cenario) == [(feito, "cliente")]
    [registro] = handoffs(cenario)
    assert registro["id"] == atendimento
    assert registro["acoes"][-1] == {
        "acao": "desbloquear_cartao", "resultado": f"{feito}: desfeito pelo cliente"
    }  # fmt: skip


def test_atendente_desfaz_no_console_e_o_caso_ligado_ao_bloqueio_fica_sabendo(cenario):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", "cadastrado")
        relato = dizer(http, auth, abrir_conversa(http, auth, "es"), "me robaron la tarjeta")
        resposta = http.post(f"/atendimento/bloqueios/{relato['bloqueio']}/desbloqueio")
    assert (resposta.status_code, resposta.json()["atendimento"]) == (200, relato["atendimento"])
    [registro] = handoffs(cenario)
    assert registro["acoes"][-1] == {
        "acao": "desbloquear_cartao", "resultado": f"{relato['bloqueio']}: desfeito pelo atendente"
    }  # fmt: skip


def test_relato_com_cartao_ja_bloqueado_por_aqui_liga_o_bloqueio_ao_caso(cenario):
    """O cartão já estava bloqueado a pedido do cliente: o relato liga esse bloqueio ao caso, que
    fica sabendo se o cliente o desfizer depois."""
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        feito = dizer(http, auth, conversa, "quiero bloquear mi tarjeta")["bloqueio"]
        relato = dizer(http, auth, conversa, "me robaron la tarjeta")
        outra = abrir_conversa(http, auth, "es")
        dizer(http, auth, outra, "quiero desbloquear mi tarjeta")
        dizer(http, auth, outra, "sí")
    [registro] = handoffs(cenario)
    assert registro["id"] == relato["atendimento"]
    assert registro["acoes"][-1] == {
        "acao": "desbloquear_cartao", "resultado": f"{feito}: desfeito pelo cliente"
    }  # fmt: skip


def test_prazo_que_vence_antes_do_sim_leva_ao_atendente(cenario):
    """A política é reavaliada no sim, com o bloqueio relido: o prazo pode ter vencido."""
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, "quiero bloquear mi tarjeta")
        dizer(http, auth, conversa, "quiero desbloquear mi tarjeta")
        with conexao(cenario) as con:
            con.execute(
                text("UPDATE app.bloqueios SET reversivel_ate = now() - interval '1 second'")
            )
        turno = dizer(http, auth, conversa, "sí")
    assert (turno["regra"], turno["acao"]) == ("POL-BLQ-05", "humano")
    assert desfeitos(cenario) == []


def test_varios_bloqueados_pergunta_qual_desbloquear(cenario):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-A", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, "bloqueen la tarjeta terminada en 9241")
        segundo = dizer(http, auth, conversa, "bloqueen la tarjeta terminada en 5678")["bloqueio"]
        pergunta = dizer(http, auth, conversa, "quiero desbloquear mi tarjeta")
        proposta = dizer(http, auth, conversa, "2")
    assert (pergunta["regra"], pergunta["estado"]) == ("POL-BLQ-06", "escolhendo_cartao")
    assert pergunta["resposta"] == (
        "¿Cuál tarjeta quieres desbloquear?\n1. tarjeta de crédito terminada en 9241\n"
        "2. tarjeta de débito terminada en 5678\nResponde con el número de la opción o con los 4"
        " últimos dígitos."
    )
    assert (proposta["regra"], proposta["estado"]) == ("POL-BLQ-04", "confirmando_desbloqueio")
    assert f"(referencia {segundo})" in proposta["resposta"]


def test_nao_na_escolha_cancela_e_outro_pedido_sai_da_etapa(cenario):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-A", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, "quiero bloquear mi tarjeta")
        cancelado = dizer(http, auth, conversa, "no")
        dizer(http, auth, conversa, "quiero bloquear mi tarjeta")
        outro = dizer(http, auth, conversa, "¿por qué rechazaron mi compra?")
    assert (cancelado["regra"], cancelado["estado"]) == ("CANCELADO", "livre")
    assert cancelado["resposta"] == "Listo, no bloqueé ninguna tarjeta. ¿Te ayudo con algo más?"
    assert outro["estado"] != "escolhendo_cartao"
    assert outro["regra"].startswith("POL-CON")
    assert bloqueios(cenario) == []


def test_escolha_nao_entendida_pergunta_de_novo_e_depois_oferece_o_atendente(cenario):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-A", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, "quiero bloquear mi tarjeta")
        de_novo = dizer(http, auth, conversa, "esa")
        oferta = dizer(http, auth, conversa, "la otra")
    assert (de_novo["regra"], de_novo["estado"]) == ("POL-BLQ-06", "escolhendo_cartao")
    assert (oferta["regra"], oferta["acao"], oferta["estado"]) == (
        "POL-HUM-03", "oferecer_humano", "oferecendo_humano"
    )  # fmt: skip
    assert oferta["resposta"].startswith("Entendí que quieres bloquear una tarjeta")
    assert bloqueios(cenario) == []


def test_bloqueio_que_nao_se_confirma_desfaz_o_turno_e_nao_diz_que_bloqueou(cenario):
    descartar = (
        "create function app.descartar() returns trigger language plpgsql as"
        " $$ begin return null; end $$;"
        " create trigger descarte_injetado before insert on app.bloqueios"
        " for each row execute function app.descartar()"
    )
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        with conexao(cenario) as con:
            con.execute(text(descartar))
        resposta = http.post(
            f"/conversas/{conversa}/turnos", json={"texto": "bloquear mi tarjeta"}, headers=auth
        )
        historico = http.get(f"/conversas/{conversa}", headers=auth).json()
    assert resposta.status_code == 503
    assert "nada foi criado" in resposta.json()["detail"]
    assert historico["turnos"] == []
    assert bloqueios(cenario) == []
    with conexao(cenario) as con:
        erros = con.execute(text("SELECT erro FROM app.eventos WHERE tipo = 'erro'")).scalars()
        assert list(erros) == ["RuntimeError"]


def test_pedido_que_cita_cartao_nao_bloqueavel_nao_bloqueia_outro_no_lugar(cenario):
    """ACH-111: com um só cartão bloqueável, citar o cartão fechado não bloqueia o outro."""
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-A", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, "bloqueen la tarjeta terminada en 5678")
        citado = dizer(http, auth, conversa, "bloqueen la tarjeta terminada en 0000")
    assert (citado["regra"], citado["acao"], citado["bloqueio"]) == (
        "POL-BLQ-03",
        "responder",
        None,
    )
    assert citado["resposta"] == (
        "Tu tarjeta de crédito terminada en 0000 no está activa, así que no la bloqueé."
    )
    assert [b["product_id"] for b in bloqueios(cenario)] == ["CRT-A2"]


def test_citar_cartao_ja_bloqueado_por_aqui_nao_bloqueia_outro(cenario):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-A", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        feito = dizer(http, auth, conversa, "bloqueen la tarjeta terminada en 5678")["bloqueio"]
        de_novo = dizer(http, auth, conversa, "bloqueen la tarjeta terminada en 5678")
    assert (de_novo["regra"], de_novo["bloqueio"]) == ("POL-BLQ-03", None)
    assert de_novo["resposta"] == (
        f"Tu tarjeta de débito terminada en 5678 ya está bloqueada (referencia {feito})."
    )
    assert [b["product_id"] for b in bloqueios(cenario)] == ["CRT-A2"]


def test_citacao_que_nao_e_de_nenhum_cartao_pergunta_em_vez_de_bloquear(cenario):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", "cadastrado")
        turno = dizer(
            http, auth, abrir_conversa(http, auth, "es"), "bloqueen la tarjeta terminada en 1234"
        )
    assert (turno["regra"], turno["estado"]) == ("POL-BLQ-06", "escolhendo_cartao")
    assert "1. tarjeta de crédito terminada en 1111" in turno["resposta"]
    assert bloqueios(cenario) == []


def test_fraude_que_cita_cartao_nao_bloqueavel_encaminha_sem_bloquear_outro(cenario):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-A", "cadastrado")
        dizer(http, auth, abrir_conversa(http, auth, "es"), "bloqueen la tarjeta terminada en 5678")
        turno = dizer(
            http, auth, abrir_conversa(http, auth, "es"), "me robaron la tarjeta terminada en 0000"
        )
    assert (turno["regra"], turno["acao"], turno["bloqueio"]) == ("POL-HUM-01", "humano", None)
    assert turno["resposta"].startswith(
        "Tu tarjeta de crédito terminada en 0000 no está activa, así que no la bloqueé.\n"
        "Por seguridad, un agente va a atender este caso."
    )
    assert [b["product_id"] for b in bloqueios(cenario)] == ["CRT-A2"]


def test_desbloqueio_que_cita_cartao_sem_bloqueio_nao_propoe_desfazer_outro(cenario):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-A", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, "bloqueen la tarjeta terminada en 9241")
        turno = dizer(http, auth, conversa, "quiero desbloquear la tarjeta terminada en 5678")
    assert (turno["regra"], turno["acao"]) == ("POL-BLQ-05", "humano")
    assert desfeitos(cenario) == []


def test_caso_de_um_cliente_nao_liga_bloqueio_de_outro(cenario):
    with cliente(cenario) as http:
        a = entrar(http, "CLI-A", "cadastrado")
        dizer(http, a, abrir_conversa(http, a, "es"), "bloqueen la tarjeta terminada en 5678")
        b = entrar(http, "CLI-B", "cadastrado")
        relato = dizer(http, b, abrir_conversa(http, b, "es"), "me robaron la tarjeta")
    por_cliente = {x["customer_id"]: x["atendimento"] for x in bloqueios(cenario)}
    assert por_cliente == {"CLI-A": None, "CLI-B": relato["atendimento"]}
