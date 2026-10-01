"""Acesso dos jurados (PRD-009) pela API real: com a senha configurada, só a saúde e o próprio
acesso respondem sem o cookie de acesso; sem senha, o portão fica desligado e nada muda
(desenvolvimento, CI e as suítes da validação)."""

import time

import pytest
from conftest import cliente
from pydantic import SecretStr, ValidationError

from jeje import acesso
from jeje.config import Settings

SENHA = "senha-de-teste-dos-jurados-2026"


@pytest.fixture
def com_senha(base):
    return base.model_copy(update={"acesso_senha": SecretStr(SENHA)})


def test_sem_senha_o_portao_fica_desligado(base):
    with cliente(base) as http:
        assert http.get("/personas").status_code == 200
        assert http.get("/acesso").json() == {"restrito": False, "liberado": True}


@pytest.mark.parametrize(
    "rota", ["/personas", "/docs", "/openapi.json", "/metricas", "/atendimento/fila"]
)
def test_com_senha_toda_rota_exige_o_cookie_de_acesso(com_senha, rota):
    with cliente(com_senha) as http:
        resposta = http.get(rota)
    assert (resposta.status_code, resposta.json()) == (401, {"detail": "acesso_restrito"})


def test_saude_e_o_proprio_acesso_respondem_sem_o_cookie(com_senha):
    with cliente(com_senha) as http:
        assert http.get("/health").status_code == 200
        assert http.get("/health/ready").status_code != 401
        assert http.get("/acesso").json() == {"restrito": True, "liberado": False}


def test_senha_certa_libera_com_cookie_httponly_e_a_errada_nao(com_senha):
    with cliente(com_senha) as http:
        errada = http.post("/acesso", json={"senha": "chute"})
        fechado = http.get("/personas").status_code
        certa = http.post("/acesso", json={"senha": SENHA})
        aberto = http.get("/personas").status_code
        situacao = http.get("/acesso").json()
    assert (errada.status_code, errada.json()) == (401, {"detail": "senha_incorreta"})
    assert (fechado, certa.status_code, aberto) == (401, 204, 200)
    cookie = certa.headers["set-cookie"]
    assert cookie.startswith(f"{acesso.COOKIE}=")
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/" in cookie
    assert "Secure" not in cookie  # fora da publicação (HTTPS), o cookie seguro não volta
    assert SENHA not in cookie
    assert situacao == {"restrito": True, "liberado": True}


def test_cookie_vencido_adulterado_ou_de_outra_senha_nao_libera(com_senha):
    agora = time.time()
    valido = acesso.emitir(SENHA, agora, 3600)
    expira, _, assinatura = valido.partition(".")
    recusados = {
        "vencido": acesso.emitir(SENHA, agora - 7200, 3600),
        "adulterado": f"{int(expira) + 999_999}.{assinatura}",
        "de outra senha": acesso.emitir("outra-senha-qualquer-de-teste", agora, 3600),
        "lixo": "lixo",
    }
    with cliente(com_senha) as http:
        for nome, valor in recusados.items():
            http.cookies.set(acesso.COOKIE, valor)
            assert http.get("/personas").status_code == 401, nome
        http.cookies.set(acesso.COOKIE, valido)
        assert http.get("/personas").status_code == 200


def test_na_publicacao_o_cookie_e_seguro(com_senha):
    seguro = com_senha.model_copy(update={"acesso_cookie_seguro": True})
    with cliente(seguro) as http:
        assert "Secure" in http.post("/acesso", json={"senha": SENHA}).headers["set-cookie"]


@pytest.mark.parametrize(
    ("senha", "obrigatorio"),
    [("", True), ("curta-demais", False), ("curta-demais", True)],
)
def test_publicacao_sem_senha_ou_com_senha_fraca_nao_sobe(base, senha, obrigatorio):
    """Falha fechada: a publicação exige a senha, e senha curta não serve em lugar nenhum."""
    with pytest.raises(ValidationError):
        Settings(acesso_senha=senha, acesso_obrigatorio=obrigatorio)
