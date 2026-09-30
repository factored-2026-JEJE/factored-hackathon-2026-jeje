"""Recarga dos dados sem brecha (PRD-002, DEV-020i), contra o PostgreSQL e a API reais.

Enquanto a carga troca a curada, nenhuma transação da API começa: ela responde 503 na hora (sem
ficar pendurada esperando a carga), e a readiness diz que os dados estão sendo recarregados.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import abrir_conversa, autenticar, cliente, conexao, dizer, registrar_dataset
from sqlalchemy import text
from test_carga import escrever_csv

from jeje import recarga, sessao
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


# ---- Recarga com ID reaproveitado (aceite do DEV-020i) ------------------------------------------

TABELAS = ["customers", "products", "transactions"]
CLIENTES = [
    {"customer_id": "CLI-A", "first_name": "Ana", "last_name": "Alves"},
    {"customer_id": "CLI-B", "first_name": "Bia", "last_name": "Borges"},
]
PRODUTOS = [
    {"product_id": f"PRD-{c}", "customer_id": f"CLI-{c}", "product_type": "Cuenta Ahorro",
     "currency": "USD", "product_status": "Active"}
    for c in "AB"
]  # fmt: skip


def _trx(tid: str, dono: str, valor: str, comercio: str, quando: str) -> dict:
    return {
        "transaction_id": tid, "customer_id": f"CLI-{dono}", "product_id": f"PRD-{dono}",
        "transaction_date": quando, "amount": valor, "currency": "USD",
        "merchant_name": comercio, "transaction_status": "Approved",
    }  # fmt: skip


def publicar(raiz, manifestos, transacoes: list[dict]) -> None:
    escrever_csv(raiz, "customers.csv", "customers", CLIENTES)
    escrever_csv(raiz, "products.csv", "products", PRODUTOS)
    escrever_csv(raiz, "transactions/year=2025/month=03/day=10/t.csv", "transactions", transacoes)
    manifesto.escrever(manifestos, manifesto.gerar(raiz, TABELAS))


def test_recarga_com_id_reaproveitado_encerra_o_atendimento_sem_brecha(banco_migrado, tmp_path):
    """A TRX-X de A passa a ser de B e a TRX-Z de A muda de valor. Depois da recarga: a conversa
    de A está encerrada e não mostra nada de B, a proposta de A não vira pré-caso, a sessão de A
    caiu, a conversa de B com atendente continua, B contesta a TRX-X normalmente e nada dá 500."""
    raiz, manifestos = tmp_path / "raw", tmp_path / "manifesto"
    publicar(raiz, manifestos, [
        _trx("TRX-X", "A", "45.90", "Loja Um", "2025-03-10 14:00:00"),
        _trx("TRX-Z", "A", "30.00", "Loja Dois", "2025-03-10 15:00:00"),
        _trx("TRX-B1", "B", "80.00", "Loja Tres", "2025-03-10 16:00:00"),
    ])  # fmt: skip
    carregar(banco_migrado, raiz, manifestos, TABELAS, "fixture", "p1")
    with conexao(banco_migrado) as con:
        sessao.provisionar_personas(con, 2)
    registrar = "No reconozco el cobro de 45,90 en Loja Um"
    with cliente(banco_migrado) as http:
        antes_a, antes_b = autenticar(http, "CLI-A"), autenticar(http, "CLI-B")
        conversa_a = abrir_conversa(http, antes_a, "es")
        assert dizer(http, antes_a, conversa_a, registrar)["acao"] == "propor_pre_caso"
        proposta_z = http.post("/minhas/transacoes/TRX-Z/contestacao/proposta", headers=antes_a)
        conversa_b = abrir_conversa(http, antes_b, "es")
        assert dizer(http, antes_b, conversa_b, "Me robaron la tarjeta")["estado"] == "com_humano"

        publicar(raiz, manifestos, [
            _trx("TRX-X", "B", "45.90", "Loja Um", "2025-03-10 14:00:00"),
            _trx("TRX-Z", "A", "31.00", "Loja Dois", "2025-03-10 15:00:00"),
            _trx("TRX-B1", "B", "80.00", "Loja Tres", "2025-03-10 16:00:00"),
        ])  # fmt: skip
        assert carregar(banco_migrado, raiz, manifestos, TABELAS, "fixture", "p1").carregou

        sessao_velha = http.get("/sessao", headers=antes_a)
        a, b = autenticar(http, "CLI-A"), autenticar(http, "CLI-B")
        historico_a = http.get(f"/conversas/{conversa_a}", headers=a)
        sim = http.post(f"/conversas/{conversa_a}/turnos", json={"texto": "sí"}, headers=a)
        confirmacao_z = http.post(
            f"/minhas/propostas/{proposta_z.json()['proposta']['id']}/confirmacao", headers=a
        )
        de_a = http.get("/minhas/transacoes", headers=a)
        x_para_a = http.get("/minhas/transacoes/TRX-X", headers=a)
        com_humano = http.post(f"/conversas/{conversa_b}/turnos", json={"texto": "hola"}, headers=b)
        conversa_nova_b = abrir_conversa(http, b, "es")
        proposta_b = dizer(http, b, conversa_nova_b, registrar)
        registrado_b = dizer(http, b, conversa_nova_b, "sí")
    assert proposta_z.status_code == 201
    assert (sim.status_code, sim.json()["regra"], sim.json()["transaction_id"]) == (
        200, "ENCERRADA", None
    )  # fmt: skip
    assert historico_a.json()["estado"] == "encerrada"
    assert sessao_velha.status_code == 401
    assert "Loja Um" not in sim.json()["resposta"]
    assert confirmacao_z.status_code == 409
    assert [t["transaction_id"] for t in de_a.json()] == ["TRX-Z"]
    assert x_para_a.status_code == 404
    assert (com_humano.status_code, com_humano.json()["regra"]) == (200, "COM-HUMANO")
    assert (proposta_b["transaction_id"], registrado_b["acao"]) == ("TRX-X", "registrar_pre_caso")
    with conexao(banco_migrado) as con:
        pre_casos = con.execute(text("SELECT customer_id, transaction_id FROM app.pre_casos"))
        assert [tuple(p) for p in pre_casos] == [("CLI-B", "TRX-X")]
        consulta = "SELECT efeito FROM app.eventos WHERE tipo = 'recarga' ORDER BY id"
        recargas = list(con.execute(text(consulta)).scalars())
    # Toda carga deixa trace: a primeira não tinha atendimento; a segunda encerrou a conversa de A,
    # as duas propostas pendentes e as duas sessões.
    assert recargas == ["conversas=0 propostas=0 sessoes=0", "conversas=1 propostas=2 sessoes=2"]


def test_recarga_da_mesma_versao_nao_encerra_nada(banco_migrado, tmp_path):
    raiz, manifestos = tmp_path / "raw", tmp_path / "manifesto"
    publicar(raiz, manifestos, [
        _trx("TRX-Z", "A", "30.00", "Loja Dois", "2025-03-10 15:00:00"),
        _trx("TRX-B1", "B", "80.00", "Loja Tres", "2025-03-10 16:00:00"),
    ])  # fmt: skip
    carregar(banco_migrado, raiz, manifestos, TABELAS, "fixture", "p1")
    with conexao(banco_migrado) as con:
        sessao.provisionar_personas(con, 2)
    with cliente(banco_migrado) as http:
        a = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, a, "es")
        dizer(http, a, conversa, "No reconozco el cobro de 30,00 en Loja Dois")
        assert not carregar(banco_migrado, raiz, manifestos, TABELAS, "fixture", "p1").carregou
        continua = http.get(f"/conversas/{conversa}", headers=a)
    assert (continua.status_code, continua.json()["estado"]) == (200, "confirmando")


def test_status_do_caso_depois_da_recarga_cita_so_o_registro_do_cliente(banco_migrado, tmp_path):
    """O pré-caso de A sobrevive à recarga (PRD-002), mas a TRX-X passa a ser de B. Perguntar pelo
    pedido de revisão responde o registro de A (protocolo, transação, data e estado) sem fatos da
    curada de agora e sem 500, e a transação que não é mais de A não vira foco. Com dois pré-casos,
    a lista descreve pela curada só a transação que ainda é de A (ACH-037)."""
    raiz, manifestos = tmp_path / "raw", tmp_path / "manifesto"
    b1 = _trx("TRX-B1", "B", "80.00", "Loja Tres", "2025-03-10 16:00:00")
    z = _trx("TRX-Z", "A", "30.00", "Loja Dois", "2025-03-10 15:00:00")
    x_de_a = _trx("TRX-X", "A", "45.90", "Loja Um", "2025-03-10 14:00:00")
    x_de_b = _trx("TRX-X", "B", "45.90", "Loja Um", "2025-03-10 14:00:00")
    publicar(raiz, manifestos, [x_de_a, z, b1])
    carregar(banco_migrado, raiz, manifestos, TABELAS, "fixture", "p1")
    with conexao(banco_migrado) as con:
        sessao.provisionar_personas(con, 2)
    with cliente(banco_migrado) as http:
        a = autenticar(http, "CLI-A")
        conversa = abrir_conversa(http, a, "es")
        dizer(http, a, conversa, "No reconozco el cobro de 45,90 en Loja Um")
        protocolo_x = dizer(http, a, conversa, "sí")["protocolo"]

        publicar(raiz, manifestos, [x_de_b, z, b1])
        assert carregar(banco_migrado, raiz, manifestos, TABELAS, "fixture", "p1").carregou

        a = autenticar(http, "CLI-A")
        nova = abrir_conversa(http, a, "es")
        pergunta = {"texto": "¿cómo va mi solicitud?"}
        so_um = http.post(f"/conversas/{nova}/turnos", json=pergunta, headers=a)
        seguinte = http.post(f"/conversas/{nova}/turnos", json={"texto": "¿y ahora?"}, headers=a)
        outra = abrir_conversa(http, a, "es")
        dizer(http, a, outra, "No reconozco el cobro de 30,00 en Loja Dois")
        protocolo_z = dizer(http, a, outra, "sí")["protocolo"]
        os_dois = http.post(f"/conversas/{nova}/turnos", json=pergunta, headers=a)
    assert so_um.status_code == 200, so_um.text
    assert (so_um.json()["regra"], so_um.json()["transaction_id"]) == ("POL-CASO-01", None)
    assert protocolo_x in so_um.json()["resposta"] and "TRX-X" in so_um.json()["resposta"]
    assert "Loja Um" not in so_um.json()["resposta"] and "45,90" not in so_um.json()["resposta"]
    assert seguinte.status_code == 200, seguinte.text
    assert os_dois.status_code == 200, os_dois.text
    lista = os_dois.json()["resposta"]
    assert os_dois.json()["regra"] == "POL-CASO-02"
    assert protocolo_x in lista and protocolo_z in lista
    assert "TRX-X" in lista and "Loja Dois" in lista and "Loja Um" not in lista
