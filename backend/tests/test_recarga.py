"""Recarga dos dados sem brecha (PRD-002, DEV-020i), contra o PostgreSQL e a API reais.

Enquanto a carga troca a curada, nenhuma transação da API começa: ela responde 503 na hora (sem
ficar pendurada esperando a carga), e a readiness diz que os dados estão sendo recarregados.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import abrir_conversa, autenticar, cliente, conexao, registrar_dataset
from sqlalchemy import text
from test_carga import escrever_csv

from jeje import recarga
from jeje.dados import manifesto
from jeje.dados.carga import CargaInvalida, carregar
from jeje.db import create_db_engine

ESPERANDO_A_TRAVA = (
    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
    " AND wait_event_type = 'Lock' AND wait_event = 'advisory'"
)


def aguardar(condicao, limite_s: float = 5) -> bool:
    fim = time.monotonic() + limite_s
    while time.monotonic() < fim:
        if condicao():
            return True
        time.sleep(0.02)
    return False


def versao_carregada(settings) -> tuple[str, str] | None:
    with conexao(settings) as con:
        return con.execute(text("SELECT version, pipeline FROM meta.dataset_version")).first()


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


def test_carga_espera_a_transacao_da_api_em_curso_e_so_depois_troca_os_dados(
    banco_migrado, tmp_path
):
    raiz, manifestos = tmp_path / "raw", tmp_path / "manifesto"
    escrever_csv(raiz, "branches.csv", "branches", [{"branch_id": "SUC-1"}])
    manifesto.escrever(manifestos, manifesto.gerar(raiz, ["branches"]))
    carregar(banco_migrado, raiz, manifestos, ["branches"], "fixture", "p1")
    anterior = tuple(versao_carregada(banco_migrado))

    api = create_db_engine(banco_migrado)
    recarga.proteger(api)
    pegou, liberar = threading.Event(), threading.Event()

    def transacao_da_api():
        with api.begin() as con:
            con.execute(text("SELECT 1"))
            pegou.set()
            liberar.wait(10)

    try:
        with ThreadPoolExecutor(max_workers=2) as fundo:
            em_curso = fundo.submit(transacao_da_api)
            assert pegou.wait(5)
            # Mesmos arquivos, pipeline novo: a carga refaz tudo, mas só depois da API terminar.
            carga = fundo.submit(
                carregar, banco_migrado, raiz, manifestos, ["branches"], "fixture", "p2"
            )
            esperou = aguardar(lambda: _esperando(banco_migrado))
            durante = tuple(versao_carregada(banco_migrado))
            liberar.set()
            em_curso.result(timeout=10)
            assert carga.result(timeout=30).carregou
    finally:
        liberar.set()
        api.dispose()
    assert esperou
    assert durante == anterior
    assert tuple(versao_carregada(banco_migrado))[1] == "p2"


def _esperando(settings) -> bool:
    with conexao(settings) as con:
        return con.execute(text(ESPERANDO_A_TRAVA)).scalar_one() > 0


def test_carga_desiste_sem_alterar_nada_se_a_api_segura_os_dados_alem_do_limite(
    banco_migrado, tmp_path, monkeypatch
):
    raiz, manifestos = tmp_path / "raw", tmp_path / "manifesto"
    escrever_csv(raiz, "branches.csv", "branches", [{"branch_id": "SUC-1"}])
    manifesto.escrever(manifestos, manifesto.gerar(raiz, ["branches"]))
    carregar(banco_migrado, raiz, manifestos, ["branches"], "fixture", "p1")
    anterior = tuple(versao_carregada(banco_migrado))
    monkeypatch.setattr(recarga, "ESPERA_DA_CARGA_S", 1)
    api = create_db_engine(banco_migrado)
    recarga.proteger(api)
    try:
        with api.begin() as presa:
            presa.execute(text("SELECT 1"))  # transação da API parada no meio
            with pytest.raises(CargaInvalida, match="em uso há mais de 1 s; nada foi alterado"):
                carregar(banco_migrado, raiz, manifestos, ["branches"], "fixture", "p2")
    finally:
        api.dispose()
    assert tuple(versao_carregada(banco_migrado)) == anterior
