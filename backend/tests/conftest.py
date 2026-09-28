"""Fixtures compartilhadas. Tudo roda contra o PostgreSQL real do compose de testes (db-test)."""

import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text
from sqlalchemy.engine import make_url

from jeje import sessao
from jeje.api import create_app
from jeje.config import Settings
from jeje.dados.qualidade import curar
from jeje.db import create_db_engine

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def alembic_config(settings: Settings) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["settings"] = settings
    return config


@contextmanager
def conexao(settings: Settings) -> Iterator[Connection]:
    """Conexão em transação (commit ao sair) com engine descartado ao final: sem conexões órfãs."""
    engine = create_db_engine(settings)
    try:
        with engine.begin() as con:
            yield con
    finally:
        engine.dispose()


@contextmanager
def cliente(settings: Settings) -> Iterator[TestClient]:
    """Cliente HTTP da aplicação real, com lifespan (abre e fecha o pool do banco)."""
    with TestClient(create_app(settings.model_copy(update={"api_root_path": ""}))) as http:
        yield http


@contextmanager
def servidor_http(settings: Settings) -> Iterator[str]:
    """Uvicorn real numa porta efêmera, com lifespan; devolve a URL base."""
    app = create_app(settings.model_copy(update={"api_root_path": ""}))
    servidor = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
    )
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    limite = time.monotonic() + 10
    while not servidor.started:
        if time.monotonic() > limite or not thread.is_alive():
            raise RuntimeError("servidor de teste não iniciou")
        time.sleep(0.01)
    porta = servidor.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{porta}"
    finally:
        servidor.should_exit = True
        thread.join(timeout=10)


def registrar_dataset(settings: Settings, version: str, source: str) -> None:
    """Registra diretamente no banco uma versão de dataset carregada (estado de teste)."""
    with conexao(settings) as con:
        con.execute(
            text("insert into meta.dataset_version (id, version, source) values (1, :v, :s)"),
            {"v": version, "s": source},
        )


@pytest.fixture
def banco_limpo():
    """Banco vazio e exclusivo do teste, criado no db-test e removido ao final."""
    base = Settings()
    url = make_url(base.database_url)
    nome = f"t_{uuid.uuid4().hex[:12]}"
    admin = create_db_engine(base).execution_options(isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as con:
            con.execute(text(f'CREATE DATABASE "{nome}"'))
        url_teste = url.set(database=nome).render_as_string(hide_password=False)
        yield base.model_copy(update={"database_url": url_teste})
        with admin.connect() as con:
            con.execute(text(f'DROP DATABASE "{nome}" WITH (FORCE)'))
    finally:
        admin.dispose()


@pytest.fixture
def banco_migrado(banco_limpo):
    """Banco exclusivo já no schema mais recente (alembic upgrade head)."""
    command.upgrade(alembic_config(banco_limpo), "head")
    return banco_limpo


# ---- Dados raw escritos direto no banco (texto, como vêm dos CSV) e curadoria ------------------

LINHA = iter(range(1, 1_000_000))


def inserir_raw(con, tabela: str, **valores) -> None:
    colunas = [*valores, "_arquivo", "_linha"]
    parametros = {**valores, "_arquivo": f"{tabela}.csv", "_linha": next(LINHA)}
    con.execute(
        text(
            f"insert into raw.{tabela} ({', '.join(colunas)}) "
            f"values ({', '.join(':' + c for c in colunas)})"
        ),
        parametros,
    )


def raw_cliente(con, cid: str, **extra) -> None:
    inserir_raw(con, "customers", customer_id=cid, **extra)


def raw_produto(con, pid: str, dono: str, **extra) -> None:
    campos = {"product_type": "Cuenta Ahorro", "currency": "USD", "product_status": "Active"}
    inserir_raw(con, "products", product_id=pid, customer_id=dono, **{**campos, **extra})


def raw_transacao(con, tid: str, cliente_id: str, produto_id: str, **extra) -> None:
    campos = {
        "transaction_date": "2025-03-10 14:09:12", "amount": "189.77", "currency": "USD",
        "transaction_status": "Approved",
    }  # fmt: skip
    chaves = {"transaction_id": tid, "customer_id": cliente_id, "product_id": produto_id}
    inserir_raw(con, "transactions", **chaves, **{**campos, **extra})


def curar_tudo(settings) -> dict:
    with conexao(settings) as con:
        cursor = con.connection.driver_connection.cursor()
        return curar(cursor, ["branches", "customers", "products", "transactions", "complaints"])


@pytest.fixture
def base(banco_migrado):
    """Dois clientes com um produto cada (CLI-A/PRD-A, CLI-B/PRD-B), só na raw."""
    with conexao(banco_migrado) as con:
        raw_cliente(con, "CLI-A")
        raw_cliente(con, "CLI-B")
        raw_produto(con, "PRD-A", "CLI-A")
        raw_produto(con, "PRD-B", "CLI-B")
    return banco_migrado


@pytest.fixture
def curada(base):
    """Base curada: CLI-A (Approved+Declined), CLI-C (Approved+Pending), CLI-B (Approved)."""
    with conexao(base) as con:
        raw_cliente(con, "CLI-C", first_name="Ana", last_name="Souza")
        raw_produto(con, "PRD-C", "CLI-C")
        raw_transacao(con, "TRX-A1", "CLI-A", "PRD-A")
        raw_transacao(con, "TRX-A2", "CLI-A", "PRD-A", transaction_status="Declined")
        raw_transacao(con, "TRX-C1", "CLI-C", "PRD-C")
        raw_transacao(con, "TRX-C2", "CLI-C", "PRD-C", transaction_status="Pending")
        raw_transacao(con, "TRX-B1", "CLI-B", "PRD-B")
    curar_tudo(base)
    return base


def quarentena(settings, tabela: str) -> dict[str, list[str]]:
    with conexao(settings) as con:
        linhas = con.execute(
            text("select registro, motivos from quality.quarentena where tabela = :t"),
            {"t": tabela},
        ).all()
    chave = {"transactions": "transaction_id", "customers": "customer_id"}.get(
        tabela, "complaint_id"
    )
    return {registro[chave]: sorted(motivos) for registro, motivos in linhas}


# ---- Conversa (G10/G11) ---------------------------------------------------------------------


@pytest.fixture
def cenario_conversa(base):
    """Conversa (G10): CLI-A com seis transações de status e comércios distintos; CLI-B com uma
    idêntica à TRX-A1 (mesmo valor, data e comércio) para provar o isolamento."""
    with conexao(base) as con:
        a = {"cliente_id": "CLI-A", "produto_id": "PRD-A"}
        raw_transacao(
            con,
            "TRX-A1",
            **a,
            transaction_date="2025-03-10 14:09:12",
            amount="45.90",
            merchant_name="Streaming Plus",
        )
        raw_transacao(
            con,
            "TRX-A2",
            **a,
            transaction_date="2025-03-12 09:00:00",
            amount="189900.55",
            currency="COP",
            merchant_name="Almacenes Éxito",
            transaction_status="Declined",
            response_code="51",
        )
        raw_transacao(
            con,
            "TRX-A3",
            **a,
            transaction_date="2025-03-14 18:30:00",
            amount="20.00",
            merchant_name="Uber",
            transaction_status="Declined",
        )
        raw_transacao(
            con,
            "TRX-A4",
            **a,
            transaction_date="2025-03-15 11:00:00",
            amount="7500.00",
            merchant_name="Boutique Moda",
        )
        raw_transacao(
            con,
            "TRX-A5",
            **a,
            transaction_date="2025-03-16 08:15:00",
            amount="12.00",
            merchant_name="Café Central",
            transaction_status="Pending",
        )
        raw_transacao(
            con,
            "TRX-A6",
            **a,
            transaction_date="2025-03-11 20:00:00",
            amount="45.90",
            merchant_name="Cine Premium",
        )
        # Compra noturna pelo app acima do limite noturno por transação (POL-HUM-04), mais antiga
        # que as outras: não entra nas listas de opções dos demais testes.
        raw_transacao(
            con,
            "TRX-A7",
            **a,
            transaction_date="2025-03-09 23:10:00",
            amount="1500.00",
            merchant_name="Farmacia Salud",
            channel="App",
        )
        # Mesmo valor, data e comércio do TRX-A1, mas de outro cliente.
        raw_transacao(con, "TRX-B1", "CLI-B", "PRD-B", transaction_date="2025-03-10 14:09:12",
                      amount="45.90", merchant_name="Streaming Plus")  # fmt: skip
    curar_tudo(base)
    with conexao(base) as con:
        sessao.provisionar_personas(con, 2)
    return base


def autenticar(http, customer_id: str) -> dict:
    token = http.post("/sessoes", json={"customer_id": customer_id}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def abrir_conversa(http, auth, idioma: str) -> str:
    resposta = http.post("/conversas", json={"idioma": idioma}, headers=auth)
    assert resposta.status_code == 201
    return resposta.json()["conversa_id"]


def dizer(http, auth, conversa: str, mensagem: str) -> dict:
    resposta = http.post(f"/conversas/{conversa}/turnos", json={"texto": mensagem}, headers=auth)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()
