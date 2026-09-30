"""Bloqueio de cartão na conversa (PRD-007), pela API real: o pedido e o relato de fraude bloqueiam
pelo dispositivo da sessão (nunca pelo chat), com vários cartões pergunta qual, a fraude sempre
chega ao atendente e o desbloqueio fica com ele — sempre conferindo o banco, não só a resposta."""

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
                "SELECT id, customer_id, product_id, tipo, motivo, dispositivo, desfeito_em"
                " FROM app.bloqueios ORDER BY id"
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
    assert feito["dispositivo"] == "cadastrado"
    # O aviso ao atendente é o bloqueio no console; ninguém é encaminhado.
    assert [b["id"] for b in console] == [feito["id"]]
    assert handoffs(cenario) == []
    # O turno é o próprio bloqueio (efeito do turno): nenhum evento `acao` a mais.
    with conexao(cenario) as con:
        consulta = "SELECT acao, efeito FROM app.eventos WHERE tipo = 'turno'"
        assert [tuple(e) for e in con.execute(text(consulta))] == [("bloquear_cartao", feito["id"])]
    assert acoes_de_bloqueio(cenario) == []


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
    assert {"acao": "bloquear_cartao",
            "resultado": f"{feito['id']}: bloqueio {tipo} do cartão de crédito final 1111"
            } in registro["acoes"]  # fmt: skip
    assert acoes_de_bloqueio(cenario) == [
        ("POL-HUM-01", feito["id"], ["curated.products", "app.bloqueios"])
    ]


@pytest.mark.parametrize(
    ("resposta", "bloqueado"),
    [("1", "CRT-A1"), ("no sé cuál fue", None), ("¿por qué rechazaron mi compra?", None)],
)
def test_fraude_com_varios_cartoes_pergunta_qual_e_sempre_encaminha(cenario, resposta, bloqueado):
    """A fraude nunca fica parada: com o cartão identificado, bloqueia e encaminha; sem ele,
    encaminha sem bloquear e diz isso."""
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-A", "cadastrado")
        conversa = abrir_conversa(http, auth, "es")
        pergunta = dizer(http, auth, conversa, "me clonaron una tarjeta")
        antes = handoffs(cenario)
        seguinte = dizer(http, auth, conversa, resposta)
    assert (pergunta["regra"], pergunta["estado"]) == ("POL-BLQ-06", "escolhendo_cartao")
    assert pergunta["resposta"].startswith("Por seguridad, voy a bloquear la tarjeta afectada.")
    assert antes == []
    assert (seguinte["regra"], seguinte["acao"], seguinte["estado"]) == (
        "POL-HUM-01", "humano", "com_humano"
    )  # fmt: skip
    [registro] = handoffs(cenario)
    assert registro["pedido"] == "me clonaron una tarjeta"
    assert [b["product_id"] for b in bloqueios(cenario)] == ([bloqueado] if bloqueado else [])
    if bloqueado is None:
        assert seguinte["resposta"].startswith(
            "No identifiqué cuál tarjeta, así que no bloqueé ninguna.\nPor seguridad, un agente"
        )
        assert {"acao": "bloquear_cartao",
                "resultado": "cartão não identificado na resposta; nada bloqueado"
                } in registro["acoes"]  # fmt: skip


def test_fraude_sem_cartao_ativo_so_encaminha(cenario):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-C", "cadastrado")
        turno = dizer(http, auth, abrir_conversa(http, auth, "pt"), "roubaram meu cartão")
    assert (turno["regra"], turno["acao"], turno["bloqueio"]) == ("POL-HUM-01", "humano", None)
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


@pytest.mark.parametrize(
    ("bloquear", "ajuste", "motivo"),
    [
        ("me robaron la tarjeta", None, "bloqueio por relato de roubo ou perda"),
        ("quiero bloquear mi tarjeta", "now() - interval '1 second'", "fora do prazo de reversão"),
    ],
)
def test_bloqueio_por_roubo_ou_fora_do_prazo_so_o_atendente_desfaz(
    cenario, bloquear, ajuste, motivo
):
    with cliente(cenario) as http:
        auth = entrar(http, "CLI-B", "cadastrado")
        dizer(http, auth, abrir_conversa(http, auth, "es"), bloquear)
        if ajuste:
            with conexao(cenario) as con:
                con.execute(text(f"UPDATE app.bloqueios SET reversivel_ate = {ajuste}"))
        turno = dizer(http, auth, abrir_conversa(http, auth, "es"), "quiero desbloquear mi tarjeta")
    assert (turno["regra"], turno["acao"], turno["estado"]) == (
        "POL-BLQ-05", "humano", "com_humano"
    )  # fmt: skip
    assert handoffs(cenario)[-1]["pendencias"] == [
        f"Revisar pedido de desbloqueio de cartão ({motivo})"
    ]
    assert desfeitos(cenario) == []


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
