"""Pré-caso de contestação pela API real: idempotência, concorrência, validade, mudança de
situação e falha de persistência — sempre conferindo o estado do banco, não só a resposta."""

from concurrent.futures import ThreadPoolExecutor

import httpx2 as httpx
import pytest
from conftest import cliente, conexao, curar_tudo, raw_transacao, servidor_http
from sqlalchemy import text

from jeje import sessao


@pytest.fixture
def cenario(base):
    with conexao(base) as con:
        raw_transacao(con, "TRX-OK", "CLI-A", "PRD-A", amount="189.77")
        raw_transacao(
            con, "TRX-REC", "CLI-A", "PRD-A", transaction_status="Declined", response_code="51"
        )
        raw_transacao(con, "TRX-B", "CLI-B", "PRD-B", amount="10.00")
    curar_tudo(base)
    with conexao(base) as con:
        sessao.provisionar_personas(con, 2)
    return base


PROPOR = "/minhas/transacoes/{}/contestacao/proposta"
CONFIRMAR = "/minhas/propostas/{}/confirmacao"


def autenticar(http, customer_id: str) -> dict:
    token = http.post("/sessoes", json={"customer_id": customer_id}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def pre_casos(settings) -> list[tuple]:
    with conexao(settings) as con:
        return [
            tuple(r)
            for r in con.execute(
                text("select customer_id, transaction_id from app.pre_casos order by protocolo")
            )
        ]


def test_proposta_confirmada_gera_um_protocolo_relido_do_banco(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        avaliacao = http.post(PROPOR.format("TRX-OK"), headers=auth)
        assert avaliacao.status_code == 201
        assert avaliacao.json()["decisao"]["regra"] == "POL-DISP-01"
        proposta = avaliacao.json()["proposta"]["id"]
        confirmacao = http.post(f"/minhas/propostas/{proposta}/confirmacao", headers=auth)
        assert confirmacao.status_code == 201
        protocolo = confirmacao.json()["protocolo"]
        assert protocolo.startswith("PC-")
        assert [p["protocolo"] for p in http.get("/minhas/pre-casos", headers=auth).json()] == [
            protocolo
        ]
    assert pre_casos(cenario) == [("CLI-A", "TRX-OK")]


def test_confirmar_de_novo_devolve_o_mesmo_protocolo_sem_duplicar(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        proposta = http.post(PROPOR.format("TRX-OK"), headers=auth).json()
        url = CONFIRMAR.format(proposta["proposta"]["id"])
        primeira, segunda = http.post(url, headers=auth), http.post(url, headers=auth)
        assert (primeira.status_code, segunda.status_code) == (201, 200)
        assert primeira.json() == segunda.json()
        # Nova avaliação da mesma transação devolve o protocolo existente, sem nova proposta.
        de_novo = http.post(PROPOR.format("TRX-OK"), headers=auth).json()
        assert de_novo["decisao"] == {"regra": "POL-DISP-03", "acao": "responder",
                                      "detalhe": primeira.json()["protocolo"]}  # fmt: skip
        assert de_novo["proposta"] is None
    assert len(pre_casos(cenario)) == 1


def test_confirmacoes_concorrentes_criam_um_unico_pre_caso(cenario):
    with servidor_http(cenario) as url, httpx.Client(base_url=url) as http:
        auth = autenticar(http, "CLI-A")
        proposta = http.post(PROPOR.format("TRX-OK"), headers=auth).json()
        alvo = f"{url}{CONFIRMAR.format(proposta['proposta']['id'])}"
        with ThreadPoolExecutor(max_workers=8) as executor:
            respostas = list(executor.map(lambda _: httpx.post(alvo, headers=auth), range(8)))
    assert sorted(r.status_code for r in respostas) == [200] * 7 + [201]
    assert len({r.json()["protocolo"] for r in respostas}) == 1
    assert len(pre_casos(cenario)) == 1


def test_duas_propostas_da_mesma_transacao_viram_um_so_pre_caso(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        propostas = [http.post(PROPOR.format("TRX-OK"), headers=auth).json() for _ in range(2)]
        ids = [p["proposta"]["id"] for p in propostas]
        protocolos = {
            http.post(CONFIRMAR.format(p), headers=auth).json()["protocolo"]
            for p in ids
        }  # fmt: skip
    assert len(protocolos) == 1
    assert len(pre_casos(cenario)) == 1


def test_contestacao_de_recusada_nao_gera_proposta(cenario):
    with cliente(cenario) as http:
        avaliacao = http.post(PROPOR.format("TRX-REC"),
                              headers=autenticar(http, "CLI-A"))  # fmt: skip
    assert avaliacao.status_code == 200
    assert avaliacao.json()["proposta"] is None
    assert avaliacao.json()["decisao"]["regra"] == "POL-DISP-02"


def test_proposta_vencida_nao_confirma(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        proposta = http.post(PROPOR.format("TRX-OK"), headers=auth).json()
        with conexao(cenario) as con:
            con.execute(
                text("update app.propostas_pre_caso set expira_em = now() - interval '1 s'")
            )
        resposta = http.post(
            f"/minhas/propostas/{proposta['proposta']['id']}/confirmacao", headers=auth
        )
    assert resposta.status_code == 409
    assert pre_casos(cenario) == []


def test_situacao_mudou_entre_proposta_e_confirmacao(cenario):
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        proposta = http.post(PROPOR.format("TRX-OK"), headers=auth).json()
        with conexao(cenario) as con:
            con.execute(text("update curated.transactions set transaction_status = 'Reversed'"
                             " where transaction_id = 'TRX-OK'"))  # fmt: skip
        resposta = http.post(
            f"/minhas/propostas/{proposta['proposta']['id']}/confirmacao", headers=auth
        )
    assert resposta.status_code == 409
    assert "POL-DISP-02" in resposta.json()["detail"]
    assert pre_casos(cenario) == []


def test_proposta_de_outro_cliente_nao_e_confirmada(cenario):
    with cliente(cenario) as http:
        proposta = http.post(PROPOR.format("TRX-OK"),
                             headers=autenticar(http, "CLI-A")).json()  # fmt: skip
        resposta = http.post(CONFIRMAR.format(proposta["proposta"]["id"]),
                             headers=autenticar(http, "CLI-B"))  # fmt: skip
        alheia = http.post(PROPOR.format("TRX-B"),
                           headers=autenticar(http, "CLI-A"))  # fmt: skip
    assert resposta.status_code == 404
    assert alheia.status_code == 404
    assert pre_casos(cenario) == []


def test_falha_ao_gravar_nao_finge_sucesso_e_nova_tentativa_cria_um(cenario):
    falhar = (
        "create function app.falhar() returns trigger language plpgsql as"
        " $$ begin raise exception 'falha injetada na persistência'; end $$;"
        " create trigger falha_injetada before insert on app.pre_casos"
        " for each row execute function app.falhar()"
    )
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        proposta = http.post(PROPOR.format("TRX-OK"), headers=auth).json()
        url = CONFIRMAR.format(proposta["proposta"]["id"])
        with conexao(cenario) as con:
            con.execute(text(falhar))
        falha = http.post(url, headers=auth)
        assert falha.status_code == 503
        assert "nada foi criado" in falha.json()["detail"]
        assert pre_casos(cenario) == []
        with conexao(cenario) as con:
            con.execute(text("drop trigger falha_injetada on app.pre_casos"))
        assert http.post(url, headers=auth).status_code == 201
    assert pre_casos(cenario) == [("CLI-A", "TRX-OK")]


def test_pre_caso_nao_move_dinheiro_nem_muda_a_transacao(cenario):
    consulta = text("select amount, transaction_status from curated.transactions"
                    " where transaction_id = 'TRX-OK'")  # fmt: skip
    with conexao(cenario) as con:
        antes = tuple(con.execute(consulta).one())
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        proposta = http.post(PROPOR.format("TRX-OK"), headers=auth).json()
        http.post(CONFIRMAR.format(proposta["proposta"]["id"]), headers=auth)
    with conexao(cenario) as con:
        assert tuple(con.execute(consulta).one()) == antes


def test_propostas_diferentes_confirmadas_ao_mesmo_tempo_so_uma_cria(cenario):
    with servidor_http(cenario) as url, httpx.Client(base_url=url) as http:
        auth = autenticar(http, "CLI-A")
        propostas = [http.post(PROPOR.format("TRX-OK"), headers=auth).json() for _ in range(6)]
        alvos = [f"{url}{CONFIRMAR.format(p['proposta']['id'])}" for p in propostas]
        with ThreadPoolExecutor(max_workers=6) as executor:
            respostas = list(executor.map(lambda alvo: httpx.post(alvo, headers=auth), alvos))
    assert sorted(r.status_code for r in respostas) == [200] * 5 + [201]
    assert len({r.json()["protocolo"] for r in respostas}) == 1
    assert len(pre_casos(cenario)) == 1


def test_avaliacao_reconhece_pre_caso_ja_aberto(cenario):
    """A avaliação (GET) e a proposta (POST) precisam concordar: achado do E2E da G8."""
    with cliente(cenario) as http:
        auth = autenticar(http, "CLI-A")
        proposta = http.post(PROPOR.format("TRX-OK"), headers=auth).json()
        protocolo = http.post(CONFIRMAR.format(proposta["proposta"]["id"]), headers=auth).json()[
            "protocolo"
        ]
        avaliacao = http.get("/minhas/transacoes/TRX-OK/contestacao", headers=auth).json()
    assert avaliacao == {"regra": "POL-DISP-03", "acao": "responder", "detalhe": protocolo}


@pytest.fixture
def noturnas(base):
    """Duas compras de USD 600 pelo app à noite: cada uma cabe no limite por transação (1.000),
    as duas juntas passam do limite do dia (1.000) do compose."""
    with conexao(base) as con:
        for tid, hora in (("TRX-N1", "21:00:00"), ("TRX-N2", "23:30:00")):
            raw_transacao(
                con, tid, "CLI-A", "PRD-A", amount="600.00", channel="App",
                transaction_date=f"2025-03-10 {hora}",
            )  # fmt: skip
    curar_tudo(base)
    with conexao(base) as con:
        sessao.provisionar_personas(con, 2)
    return base


def test_limite_do_dia_soma_o_que_ja_foi_registrado_hoje(noturnas):
    with cliente(noturnas) as http:
        auth = autenticar(http, "CLI-A")
        primeira = http.post(PROPOR.format("TRX-N1"), headers=auth).json()
        assert primeira["decisao"]["regra"] == "POL-DISP-01"
        assert (
            http.post(CONFIRMAR.format(primeira["proposta"]["id"]), headers=auth).status_code == 201
        )
        segunda = http.post(PROPOR.format("TRX-N2"), headers=auth).json()
        avaliacao = http.get("/minhas/transacoes/TRX-N2/contestacao", headers=auth).json()
    esperado = {"regra": "POL-HUM-04", "acao": "humano",
                "detalhe": "noturna digital acima do limite do dia"}  # fmt: skip
    assert (segunda["decisao"], segunda["proposta"]) == (esperado, None)
    assert avaliacao == esperado  # a avaliação sem efeito diz o mesmo que a proposta
    assert pre_casos(noturnas) == [("CLI-A", "TRX-N1")]


def test_confirmacoes_simultaneas_nao_estouram_o_limite_do_dia(noturnas):
    with servidor_http(noturnas) as url, httpx.Client(base_url=url) as http:
        auth = autenticar(http, "CLI-A")
        # As duas propostas nascem antes de qualquer registro: cada uma, sozinha, cabe no dia.
        propostas = [
            http.post(PROPOR.format(t), headers=auth).json()["proposta"]["id"]
            for t in ("TRX-N1", "TRX-N2")
        ]
        with ThreadPoolExecutor(max_workers=2) as grupo:
            respostas = list(
                grupo.map(lambda p: http.post(CONFIRMAR.format(p), headers=auth), propostas)
            )
    assert sorted(r.status_code for r in respostas) == [201, 409]
    assert len(pre_casos(noturnas)) == 1


# ---- Janela e reincidência (PRD-008) ------------------------------------------------------------


@pytest.fixture
def antigas(base):
    """Compras de CLI-A na borda da janela de contestação: o último dia dos dados é 10/03/2025, e
    10/11/2024 fica a 120 dias dele, 09/11/2024 a 121."""
    with conexao(base) as con:
        for tid, quando in (
            ("TRX-HOJE", "2025-03-10 10:00:00"),
            ("TRX-120", "2024-11-10 10:00:00"),
            ("TRX-121", "2024-11-09 10:00:00"),
        ):
            raw_transacao(con, tid, "CLI-A", "PRD-A", amount="20.00", transaction_date=quando)
    curar_tudo(base)
    with conexao(base) as con:
        sessao.provisionar_personas(con, 2)
    return base


def test_janela_de_contestacao_conta_do_ultimo_dia_dos_dados(antigas):
    """A janela é contada da base (um retrato de 2025), não do relógio: pelo relógio, toda compra
    da base estaria fora dela."""
    with cliente(antigas) as http:
        auth = autenticar(http, "CLI-A")
        na_borda = http.get("/minhas/transacoes/TRX-120/contestacao", headers=auth).json()
        fora = http.post(PROPOR.format("TRX-121"), headers=auth).json()
    assert na_borda["regra"] == "POL-DISP-01"
    assert (fora["decisao"]["regra"], fora["decisao"]["acao"], fora["proposta"]) == (
        "POL-HUM-05", "humano", None
    )  # fmt: skip
    assert pre_casos(antigas) == []


@pytest.fixture
def varias(base):
    """Cinco compras pequenas de CLI-A de dia, para registrar pré-casos em sequência."""
    with conexao(base) as con:
        for i in range(1, 6):
            raw_transacao(
                con, f"TRX-V{i}", "CLI-A", "PRD-A", amount="15.00",
                transaction_date=f"2025-03-10 1{i}:00:00",
            )  # fmt: skip
    curar_tudo(base)
    with conexao(base) as con:
        sessao.provisionar_personas(con, 2)
    return base


def registrar(http, auth, tid: str):
    proposta = http.post(PROPOR.format(tid), headers=auth).json()
    return http.post(CONFIRMAR.format(proposta["proposta"]["id"]), headers=auth)


def test_reincidencia_manda_a_quarta_contestacao_do_mes_para_o_atendente(varias):
    with cliente(varias) as http:
        auth = autenticar(http, "CLI-A")
        for tid in ("TRX-V1", "TRX-V2", "TRX-V3"):
            assert registrar(http, auth, tid).status_code == 201
        quarta = http.get("/minhas/transacoes/TRX-V4/contestacao", headers=auth).json()
    assert (quarta["regra"], quarta["acao"]) == ("POL-HUM-06", "humano")
    assert len(pre_casos(varias)) == 3


def test_pre_casos_de_mais_de_30_dias_nao_contam_na_reincidencia(varias):
    with cliente(varias) as http:
        auth = autenticar(http, "CLI-A")
        for tid in ("TRX-V1", "TRX-V2", "TRX-V3"):
            assert registrar(http, auth, tid).status_code == 201
        with conexao(varias) as con:
            con.execute(text("UPDATE app.pre_casos SET criado_em = now() - interval '31 days'"))
        quarta = http.get("/minhas/transacoes/TRX-V4/contestacao", headers=auth).json()
    assert quarta["regra"] == "POL-DISP-01"


def test_confirmacao_reavalia_a_reincidencia(varias):
    """Proposta feita com 2 pré-casos recentes; um terceiro é registrado antes do sim: a
    confirmação reavalia e responde 409, sem criar pré-caso."""
    with cliente(varias) as http:
        auth = autenticar(http, "CLI-A")
        for tid in ("TRX-V1", "TRX-V2"):
            assert registrar(http, auth, tid).status_code == 201
        proposta = http.post(PROPOR.format("TRX-V4"), headers=auth).json()
        assert proposta["decisao"]["regra"] == "POL-DISP-01"
        assert registrar(http, auth, "TRX-V3").status_code == 201
        confirmacao = http.post(CONFIRMAR.format(proposta["proposta"]["id"]), headers=auth)
    assert confirmacao.status_code == 409
    assert ("CLI-A", "TRX-V4") not in pre_casos(varias)
