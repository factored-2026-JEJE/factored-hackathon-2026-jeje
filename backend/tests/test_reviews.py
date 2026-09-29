"""Reviews das conversas de teste: gravadas no banco, ligadas à conversa do dono, e publicadas como
Issue (com a transcrição) quando há repositório e token; o GitHub aqui é um servidor falso local."""

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from conftest import abrir_conversa, autenticar, cliente, conexao, dizer
from sqlalchemy import text

from jeje import reviews as reviews_mod
from jeje.db import create_db_engine

REVIEW = {
    "avaliador": "Prism411",
    "nota": 2,
    "resolveu": "nao",
    "comentario": "Pediu o valor de novo.",
}


@pytest.fixture
def cenario(cenario_conversa):
    return cenario_conversa


def reviews(settings) -> list[dict]:
    with conexao(settings) as con:
        consulta = (
            "SELECT conversa_id, avaliador, nota, resolveu, comentario, issue_url FROM app.reviews"
        )
        return [dict(linha) for linha in con.execute(text(consulta)).mappings()]


@contextmanager
def github_falso(status: int = 201) -> Iterator[tuple[str, list[dict]]]:
    """API do GitHub falsa: guarda cada pedido e responde como a criação de Issue."""
    pedidos: list[dict] = []

    class Tratador(BaseHTTPRequestHandler):
        def do_POST(self):
            corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            pedidos.append(
                {"caminho": self.path, "autorizacao": self.headers["Authorization"], **corpo}
            )
            resposta = json.dumps({"html_url": "https://github.com/o/r/issues/7"}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(resposta)

        def log_message(self, *_):
            pass

    servidor = HTTPServer(("127.0.0.1", 0), Tratador)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{servidor.server_port}", pedidos
    finally:
        servidor.shutdown()
        servidor.server_close()


def conversar(http, auth) -> str:
    conversa = abrir_conversa(http, auth, "es")
    dizer(http, auth, conversa, "No reconozco un cobro de 45,90")
    dizer(http, auth, conversa, "no sé")
    return conversa


def test_testadores_sao_os_do_time(cenario):
    with cliente(cenario.model_copy(update={"testadores": "enzo200325, Prism411"})) as http:
        assert http.get("/testadores").json() == ["enzo200325", "Prism411"]


def test_review_sem_token_fica_no_banco_ligada_a_conversa(cenario):
    with github_falso() as (url, pedidos):
        config = cenario.model_copy(update={"github_api_url": url, "github_token": ""})
        with cliente(config) as http:
            auth = autenticar(http, "CLI-A")
            conversa = conversar(http, auth)
            resposta = http.post(f"/conversas/{conversa}/reviews", json=REVIEW, headers=auth)
    assert resposta.status_code == 201
    assert resposta.json()["issue_url"] is None
    assert pedidos == []  # sem token, nada vai para o GitHub
    assert reviews(cenario) == [{"conversa_id": conversa, **REVIEW, "issue_url": None}]


def test_review_vira_issue_com_a_transcricao(cenario):
    with github_falso() as (url, pedidos):
        config = cenario.model_copy(update={"github_api_url": url, "github_token": "tok"})
        with cliente(config) as http:
            auth = autenticar(http, "CLI-A")
            conversa = conversar(http, auth)
            resposta = http.post(f"/conversas/{conversa}/reviews", json=REVIEW, headers=auth)
    assert resposta.json()["issue_url"] == "https://github.com/o/r/issues/7"
    [pedido] = pedidos
    assert pedido["caminho"] == f"/repos/{cenario.reviews_repo}/issues"
    assert pedido["autorizacao"] == "Bearer tok"
    assert pedido["labels"] == ["review-teste"]
    assert pedido["title"] == "[review 2/5, não resolveu] No reconozco un cobro de 45,90"
    corpo = pedido["body"]
    assert "**Avaliador:** @Prism411" in corpo and "Pediu o valor de novo." in corpo
    assert "**1. Cliente:** No reconozco un cobro de 45,90" in corpo
    assert "**2. Cliente:** no sé" in corpo and "`RESUMO` · `oferecer_humano`" in corpo
    dados = json.loads(corpo.split("<!-- jeje-review\n")[1].removesuffix("\n-->"))
    assert [t["mensagem"] for t in dados["turnos"]] == ["No reconozco un cobro de 45,90", "no sé"]
    assert (dados["cliente"], dados["idioma"], dados["nota"]) == ("CLI-A", "es", 2)
    assert reviews(cenario)[0]["issue_url"] == "https://github.com/o/r/issues/7"


def test_falha_do_github_nao_perde_a_review(cenario):
    with github_falso(status=500) as (url, _):
        config = cenario.model_copy(update={"github_api_url": url, "github_token": "tok"})
        with cliente(config) as http:
            auth = autenticar(http, "CLI-A")
            conversa = conversar(http, auth)
            resposta = http.post(f"/conversas/{conversa}/reviews", json=REVIEW, headers=auth)
    assert resposta.status_code == 201 and resposta.json()["issue_url"] is None
    assert len(reviews(cenario)) == 1


def test_so_o_dono_avalia_e_so_quem_e_do_time(cenario):
    with cliente(cenario) as http:
        auth_a, auth_b = autenticar(http, "CLI-A"), autenticar(http, "CLI-B")
        conversa = conversar(http, auth_a)
        alheia = http.post(f"/conversas/{conversa}/reviews", json=REVIEW, headers=auth_b)
        estranho = http.post(
            f"/conversas/{conversa}/reviews", json={**REVIEW, "avaliador": "x"}, headers=auth_a
        )
        nota_fora = http.post(
            f"/conversas/{conversa}/reviews", json={**REVIEW, "nota": 6}, headers=auth_a
        )
    assert (alheia.status_code, estranho.status_code, nota_fora.status_code) == (404, 422, 422)
    assert reviews(cenario) == []


def test_sem_modo_demo_nao_ha_reviews(cenario):
    with cliente(cenario.model_copy(update={"modo_demo": False})) as http:
        assert http.get("/testadores").status_code == 404


def test_reviews_pendentes_sao_publicadas_depois(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        conversa = conversar(http, auth)
        http.post(f"/conversas/{conversa}/reviews", json=REVIEW, headers=auth)
    engine = create_db_engine(cenario)
    try:
        with github_falso() as (url, pedidos):
            assert reviews_mod.publicar_pendentes(engine, url, "o/r", "tok") == (1, 0)
            assert reviews_mod.publicar_pendentes(engine, url, "o/r", "tok") == (0, 0)
    finally:
        engine.dispose()
    assert len(pedidos) == 1 and "**1. Cliente:** No reconozco" in pedidos[0]["body"]
    assert reviews(cenario)[0]["issue_url"] == "https://github.com/o/r/issues/7"
