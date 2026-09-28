"""Recarga dos dados sem brecha (PRD-002, DEV-020i), contra o PostgreSQL e a API reais.

Enquanto a carga troca a curada, nenhuma transação da API começa: ela responde 503 na hora (sem
ficar pendurada esperando a carga), e a readiness diz que os dados estão sendo recarregados.
"""

import time

from conftest import abrir_conversa, autenticar, cliente, conexao, registrar_dataset
from sqlalchemy import text

from jeje import recarga


def test_durante_a_recarga_a_api_responde_503_na_hora(cenario_conversa):
    registrar_dataset(cenario_conversa, "v-teste", "fixture")
    with cliente(cenario_conversa) as http:
        auth = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, auth, "es")
        with conexao(cenario_conversa) as carga:
            # A carga segura a trava exclusiva da recarga até o commit.
            carga.execute(text("SELECT pg_advisory_xact_lock(:trava)"), {"trava": recarga.TRAVA})
            inicio = time.monotonic()
            turno = http.post(f"/conversas/{conversa}/turnos", json={"texto": "hola"}, headers=auth)
            lista = http.get("/minhas/transacoes", headers=auth)
            pronta = http.get("/health/ready")
            demorou = time.monotonic() - inicio
        depois = http.get("/minhas/transacoes", headers=auth)
    assert [turno.status_code, lista.status_code, pronta.status_code] == [503, 503, 503]
    assert turno.headers["Retry-After"] == lista.headers["Retry-After"] == "30"
    assert "atualizados" in lista.json()["detail"]
    assert pronta.json() == {"status": "unavailable", "database": "reloading", "dataset": None}
    assert demorou < 2  # nenhuma esperou a carga terminar
    assert depois.status_code == 200
