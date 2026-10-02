"""Traces do atendimento (G11) pela API real: um evento por turno, com o que o turno fez de fato,
latência medida, erro registrado mesmo quando o turno é desfeito — e nada de token ou texto."""

import json

from conftest import abrir_conversa, autenticar, cliente, conexao, dizer, registrar_dataset
from sqlalchemy import text

PEDIDO = "Me llamo Rocío y no reconozco el cobro de 45,90 en Streaming Plus"


def eventos(settings) -> list[dict]:
    with conexao(settings) as con:
        linhas = con.execute(
            text(
                "SELECT tipo, conversa_id, numero, intencao, regra, acao, efeito, fontes, erro,"
                " latencia_ms FROM app.eventos ORDER BY id"
            )
        ).mappings()
        return [dict(linha) for linha in linhas]


def turnos(settings) -> list[dict]:
    with conexao(settings) as con:
        consulta = "SELECT numero, intencao, regra, acao, efeito FROM app.turnos ORDER BY numero"
        return [dict(linha) for linha in con.execute(text(consulta)).mappings()]


def test_cada_turno_gera_um_evento_com_o_que_ele_fez(cenario_conversa):
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        proposta = dizer(http, auth, conversa, PEDIDO)
        registrado = dizer(http, auth, conversa, "sí")
    registrados = eventos(cenario_conversa)
    assert [e["tipo"] for e in registrados] == ["turno", "turno"]
    assert all(e["conversa_id"] == conversa for e in registrados)
    # O evento repete o que o turno gravou (regra, ação, efeito), não um resumo à parte.
    assert [
        {k: e[k] for k in ("numero", "intencao", "regra", "acao", "efeito")} for e in registrados
    ] == turnos(cenario_conversa)
    assert registrados[0]["efeito"] == proposta["proposta"]["id"]
    assert registrados[1]["efeito"] == registrado["protocolo"]
    assert registrados[0]["fontes"] == [
        "curated.transactions", "app.pre_casos", "app.propostas_pre_caso"
    ]  # fmt: skip
    assert registrados[1]["fontes"] == ["app.pre_casos"]


def test_evento_nao_carrega_token_nem_texto_nem_cliente(cenario_conversa):
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, PEDIDO)
        dizer(http, auth, conversa, "me robaron la tarjeta")
    token = auth["Authorization"].removeprefix("Bearer ")
    despejo = json.dumps(eventos(cenario_conversa), default=str, ensure_ascii=False)
    for proibido in (token, "Rocío", PEDIDO, "robaron", "CLI-A", "45,90"):
        assert proibido not in despejo, proibido


def test_latencia_e_medida_no_turno(cenario_conversa):
    """Com a gravação do turno atrasada 80 ms pelo banco, a latência registrada precisa refletir."""
    with conexao(cenario_conversa) as con:
        con.execute(
            text(
                "CREATE FUNCTION app.atrasar() RETURNS trigger LANGUAGE plpgsql AS"
                " $$ BEGIN PERFORM pg_sleep(0.08); RETURN NEW; END $$;"
                " CREATE TRIGGER atrasar BEFORE INSERT ON app.turnos"
                " FOR EACH ROW EXECUTE FUNCTION app.atrasar()"
            )
        )
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        dizer(http, auth, abrir_conversa(http, auth, "es"), "hola")
    [evento] = eventos(cenario_conversa)
    assert evento["latencia_ms"] >= 80


def test_erro_de_turno_desfeito_vira_evento_so_com_a_classe(cenario_conversa):
    with conexao(cenario_conversa) as con:
        con.execute(
            text(
                "CREATE FUNCTION app.falhar() RETURNS trigger LANGUAGE plpgsql AS"
                " $$ BEGIN RAISE EXCEPTION 'disco cheio para CLI-A no cobro de 45,90'; END $$;"
                " CREATE TRIGGER falhar BEFORE INSERT ON app.pre_casos"
                " FOR EACH ROW EXECUTE FUNCTION app.falhar()"
            )
        )
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, PEDIDO)
        falha = http.post(f"/conversas/{conversa}/turnos", json={"texto": "sí"}, headers=auth)
    assert falha.status_code == 503
    registrados = eventos(cenario_conversa)
    assert [e["tipo"] for e in registrados] == ["turno", "erro"]
    erro = registrados[1]
    assert (erro["conversa_id"], erro["erro"], erro["regra"], erro["efeito"]) == (
        conversa, "ProgrammingError", None, None
    )  # fmt: skip
    assert erro["latencia_ms"] > 0
    assert "disco cheio" not in json.dumps(registrados, default=str)


def test_evento_guarda_o_id_da_requisicao_que_liga_resposta_log_e_trace(cenario_conversa):
    """Quem relata um problema entrega o X-Request-ID da resposta: ele leva às linhas do log e ao
    evento do turno no banco (auditoria sem o texto do cliente)."""
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        informado = http.post(
            f"/conversas/{conversa}/turnos",
            json={"texto": PEDIDO},
            headers={**auth, "X-Request-ID": "auditoria-123"},
        )
        gerado = http.post(f"/conversas/{conversa}/turnos", json={"texto": "no"}, headers=auth)
    with conexao(cenario_conversa) as con:
        ids = list(con.execute(text("SELECT requisicao FROM app.eventos ORDER BY id")).scalars())
    assert informado.headers["X-Request-ID"] == "auditoria-123"
    assert ids == ["auditoria-123", gerado.headers["X-Request-ID"]]


def test_evento_guarda_a_versao_dos_dados_em_vigor_e_o_antigo_nao_muda(cenario_conversa):
    """DEV-044: cada evento grava a versão dos dados da hora em que aconteceu; depois de uma recarga
    (outra versão em meta.dataset_version), o evento do turno antigo continua com a sua."""
    registrar_dataset(cenario_conversa, version="versao-antiga", source="fixture")
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        dizer(http, auth, abrir_conversa(http, auth, "es"), "¿Por qué rechazaron mi compra?")
        with conexao(cenario_conversa) as con:
            con.execute(text("UPDATE meta.dataset_version SET version = 'versao-nova'"))
        dizer(http, auth, abrir_conversa(http, auth, "es"), "¿Por qué rechazaron mi compra?")
    with conexao(cenario_conversa) as con:
        versoes = (
            con.execute(
                text("SELECT versao_dos_dados FROM app.eventos WHERE tipo = 'turno' ORDER BY id")
            )
            .scalars()
            .all()
        )
    assert versoes == ["versao-antiga", "versao-nova"]
