"""Logs da API real (DEV-028): id da requisição, linha de acesso, falhas e o que nunca entra.

Tudo pela aplicação de verdade (TestClient + PostgreSQL de teste); os registros são lidos do
`caplog`. O esperado de cada linha está escrito aqui. Falha de persistência é injetada por trigger
no banco, como nos testes de pré-caso, sem tocar no código sob teste.
"""

import logging
import re

import pytest
from conftest import abrir_conversa, autenticar, cliente, conexao, dizer
from sqlalchemy import text
from sqlalchemy.exc import DataError

from jeje.config import Settings

ID_GERADO = re.compile(r"[0-9a-f]{32}")
BANCO_FORA = "postgresql+psycopg://jeje:jeje@192.0.2.1:5432/nada"


def registros(caplog, nome: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == nome]


def test_resposta_traz_id_e_o_mesmo_id_marca_acesso_e_turno_com_rota_modelo(
    cenario_conversa, caplog
):
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        caplog.clear()
        resposta = http.post(
            f"/conversas/{conversa}/turnos", json={"texto": "Me robaron la tarjeta"}, headers=auth
        )
    assert resposta.status_code == 200
    rid = resposta.headers["X-Request-ID"]
    assert ID_GERADO.fullmatch(rid)
    [acesso] = registros(caplog, "jeje.http")
    assert re.fullmatch(
        r"acesso metodo=POST rota=/conversas/\{conversa_id\}/turnos status=200 ms=\d+\.\d",
        acesso.getMessage(),
    )
    assert (acesso.levelno, acesso.req) == (logging.INFO, rid)
    [turno] = registros(caplog, "jeje.conversa")
    atendimento = resposta.json()["atendimento"]
    assert turno.getMessage() == (
        f"turno conversa={conversa} numero=1 intencao=fraude regra=POL-HUM-01 acao=humano"
        f" estado=com_humano efeito={atendimento}"
    )
    assert turno.req == rid  # o endpoint síncrono (outra thread) enxerga o id da requisição


def test_id_recebido_valido_e_reaproveitado_e_invalido_e_trocado():
    with cliente(Settings()) as http:
        valido = http.get("/health", headers={"X-Request-ID": "suporte-42.a_b"})
        longo = http.get("/health", headers={"X-Request-ID": "a" * 65})
        com_espaco = http.get("/health", headers={"X-Request-ID": "a b"})
        sem = http.get("/health")
    assert valido.headers["X-Request-ID"] == "suporte-42.a_b"
    trocados = [r.headers["X-Request-ID"] for r in (longo, com_espaco, sem)]
    assert all(ID_GERADO.fullmatch(t) for t in trocados)
    assert len(set(trocados)) == 3


def test_sonda_de_saude_ok_nao_aparece_no_nivel_info_mas_a_que_falha_aparece(caplog):
    with cliente(Settings()) as http:
        assert http.get("/health").status_code == 200
    assert registros(caplog, "jeje.http") == []
    fora = Settings(database_url=BANCO_FORA, db_connect_timeout_s=1)
    with cliente(fora) as http:
        assert http.get("/health/ready").status_code == 503
    [falha] = registros(caplog, "jeje.http")
    assert falha.levelno == logging.WARNING
    assert "rota=/health/ready status=503" in falha.getMessage()


def test_banco_fora_rota_protegida_responde_503_json_e_um_aviso_sem_traceback(caplog):
    fora = Settings(database_url=BANCO_FORA, db_connect_timeout_s=1)
    with cliente(fora) as http:
        resposta = http.get("/minhas/transacoes", headers={"Authorization": "Bearer qualquer"})
    assert resposta.status_code == 503
    assert resposta.headers["Retry-After"] == "5"
    assert resposta.json() == {
        "detail": "Serviço temporariamente indisponível. Tente de novo em instantes."
    }
    [aviso] = registros(caplog, "jeje.db")
    assert aviso.levelno == logging.WARNING and aviso.exc_info is None
    assert aviso.getMessage() == (
        "banco indisponivel erro=ConnectionTimeout motivo='connection timeout expired'"
    )


def test_erro_inesperado_vira_500_json_com_o_id_e_um_log_com_traceback(cenario_conversa, caplog):
    falhar = (
        "create function app.falhar() returns trigger language plpgsql as"
        " $$ begin raise exception 'falha injetada'; end $$;"
        " create trigger falha_injetada before update on app.handoffs"
        " for each row execute function app.falhar()"
    )
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        atendimento = dizer(http, auth, conversa, "Me robaron la tarjeta")["atendimento"]
        with conexao(cenario_conversa) as con:
            con.execute(text(falhar))
        caplog.clear()
        resposta = http.post(f"/atendimento/fila/{atendimento}/assumir")
        fila = [e["id"] for e in http.get("/atendimento/fila").json()]
    rid = resposta.headers["X-Request-ID"]
    assert resposta.status_code == 500
    assert resposta.json() == {"detail": f"Erro interno inesperado (X-Request-ID {rid})."}
    assert fila == [atendimento]  # nada foi assumido: a transação foi desfeita
    erros = [r for r in registros(caplog, "jeje.http") if r.levelno == logging.ERROR]
    assert len(erros) == 1 and erros[0].req == rid
    linhas = erros[0].getMessage().splitlines()
    assert linhas[0] == "erro inesperado metodo=POST rota=/atendimento/fila/{handoff_id}/assumir"
    # Onde e o quê (frames e classes da cadeia), sem a mensagem que o banco devolveu.
    assert any("jeje/handoff.py" in linha for linha in linhas)
    assert linhas[-1] == "sqlalchemy.exc.ProgrammingError"
    assert "psycopg.errors.RaiseException" in linhas
    assert "falha injetada" not in erros[0].getMessage()


def test_logs_nunca_trazem_mensagem_do_cliente_token_nem_cliente(cenario_conversa, caplog):
    marca = "ZEBRAXQ"  # sem dígitos: não vira valor citado na leitura da mensagem
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        dizer(http, auth, conversa, f"No reconozco el cobro de 45,90 en Streaming Plus {marca}")
        protocolo = dizer(http, auth, conversa, "Sí")["protocolo"]
        dizer(http, auth, conversa, f"Me robaron la tarjeta {marca}")
        http.get("/minhas/transacoes", headers={"Authorization": "Bearer token-errado-9911"})
    assert protocolo is not None
    texto = "\n".join(
        f"{r.getMessage()} {r.exc_text or ''}" for r in caplog.records if r.name.startswith("jeje")
    )
    token = auth["Authorization"].removeprefix("Bearer ")
    assert "turno conversa=" in texto and f"efeito={protocolo}" in texto
    for proibido in (marca, token, "token-errado-9911", "CLI-A", "Streaming Plus"):
        assert proibido not in texto


def test_erro_de_sql_nao_carrega_os_valores_dos_parametros(cenario_conversa):
    # O erro (divisão por zero) não cita o valor; só o SQLAlchemy o anexaria à mensagem.
    consulta = text("SELECT 1 / 0 WHERE CAST(:valor AS text) IS NOT NULL")
    with pytest.raises(DataError) as erro, conexao(cenario_conversa) as con:
        con.execute(consulta, {"valor": "ZEBRAXQ"})
    assert "division by zero" in str(erro.value)
    assert "ZEBRAXQ" not in str(erro.value)


def test_efeitos_confirmados_pela_api_aparecem_no_log_depois_do_commit(cenario_conversa, caplog):
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        proposta = http.post("/minhas/transacoes/TRX-A1/contestacao/proposta", headers=auth).json()[
            "proposta"
        ]
        confirmar = f"/minhas/propostas/{proposta['id']}/confirmacao"
        primeira = http.post(confirmar, headers=auth)
        repetida = http.post(confirmar, headers=auth)
        conversa = abrir_conversa(http, auth, "pt")
        atendimento = dizer(http, auth, conversa, "Roubaram meu cartão")["atendimento"]
        assert http.post(f"/atendimento/fila/{atendimento}/assumir").status_code == 200
    assert (primeira.status_code, repetida.status_code) == (201, 200)
    protocolo = primeira.json()["protocolo"]
    assert [r.getMessage() for r in registros(caplog, "jeje.pre_caso")] == [
        f"pre-caso confirmado protocolo={protocolo} novo=True",
        f"pre-caso confirmado protocolo={protocolo} novo=False",
    ]
    assert [r.getMessage() for r in registros(caplog, "jeje.atendimento")] == [
        f"encaminhamento assumido id={atendimento} regra=POL-HUM-01"
    ]
