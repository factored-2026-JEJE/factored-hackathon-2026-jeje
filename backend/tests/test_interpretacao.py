"""Interpretação baseline (G10): cada caso tem o par que deveria dar errado — frase parecida que
não pode virar a mesma intenção, confirmação ou pista."""

from dataclasses import fields
from datetime import date
from decimal import Decimal

import pytest

from jeje.interpretacao import Interpretacao, comercio_citado, interpretar

REFERENCIA = date(2026, 3, 1)


def ler(texto: str, anterior: str = "es") -> Interpretacao:
    return interpretar(texto, anterior, REFERENCIA)


@pytest.mark.parametrize(
    ("texto", "intencao"),
    [
        ("¿Por qué rechazaron mi compra?", "consultar"),
        ("Por que minha compra foi recusada?", "consultar"),
        ("No reconozco este cobro", "contestar"),
        ("não reconheço essa cobrança", "contestar"),
        ("no la reconozco", "contestar"),
        ("Me robaron la tarjeta", "fraude"),
        ("clonaram meu cartão", "fraude"),
        ("no fui yo", "fraude"),
        ("quiero hablar con un agente", "humano"),
        ("quero falar com um atendente", "humano"),
        ("necesito ayuda de una persona", "humano"),
        ("quero falar com alguém", "humano"),
        ("alguien usó mi tarjeta sin permiso", "fraude"),
        ("quiero un préstamo", "fora_de_escopo"),
        ("qual a taxa de juros?", "fora_de_escopo"),
        ("hola", "desconhecida"),
        # "robô" sem acento é "robo": não é relato de roubo.
        ("estou falando com um robô?", "desconhecida"),
    ],
)
def test_intencao_por_lingua(texto, intencao):
    lida = ler(texto)
    assert lida.intencao == intencao
    assert bool(lida.sinais) == (intencao != "desconhecida")


@pytest.mark.parametrize(
    ("texto", "intencao"),
    [
        # ACH-101: perda, extravio e assalto são relato de fraude já no primeiro turno.
        ("¡Mi tarjeta está perdida! ¿Qué puedo hacer?", "fraude"),
        ("Meu cartão foi perdido! O que posso fazer?", "fraude"),
        ("fui assaltado e levaram a carteira com os cartões", "fraude"),
        ("me asaltaron y se llevaron la billetera", "fraude"),
        ("perdí mi celular con la app del banco", "fraude"),
        ("extravié la tarjeta ayer", "fraude"),
        ("não encontro meu cartão", "fraude"),
        ("perdi o meu cartão ontem", "fraude"),
        ("mi tarjeta de crédito está perdida", "fraude"),
        # Pedido de humano pelo cargo de quem atende.
        ("posso falar com um gerente? é urgente", "humano"),
        ("quiero hablar con un ejecutivo", "humano"),
        ("necesito un supervisor", "humano"),
        # Perda sem cartão, carteira ou celular perto não é relato de fraude.
        ("perdí la conexión en la app", "desconhecida"),
        ("perdi o prazo do pagamento", "consultar"),
        ("perdi o prazo do pagamento do cartão", "consultar"),
        ("No encuentro la compra en mi tarjeta", "consultar"),
        ("não encontro a transação no meu cartão", "consultar"),
    ],
)
def test_perda_assalto_e_cargo_de_quem_atende(texto, intencao):
    assert ler(texto).intencao == intencao


@pytest.mark.parametrize(
    ("texto", "intencao"),
    [
        # Perguntar pelo reembolso ou pela devolução é consulta (ACH-102, nas regras).
        ("¿dónde está mi reembolso?", "consultar"),
        ("¿cuándo llega la devolución?", "consultar"),
        ("cadê a devolução do meu dinheiro?", "consultar"),
        # Contestação é dizer que não reconhece a cobrança ou que ela é indevida.
        ("quiero el reembolso de un cobro que no reconozco", "contestar"),
        ("quero a devolução de uma cobrança indevida", "contestar"),
    ],
)
def test_reembolso_e_consulta_e_contestacao_e_nao_reconhecer(texto, intencao):
    assert ler(texto).intencao == intencao


@pytest.mark.parametrize(
    ("texto", "intencao"),
    [
        # Cargo de quem atende citado de passagem não é pedido de humano (ACH-104).
        ("El gerente de la tienda dice que el pago no pasó, ¿por qué?", "consultar"),
        ("O gerente da loja disse que meu cartão foi recusado, por quê?", "consultar"),
        ("mi ejecutivo de cuenta me dijo que el cargo está pendiente", "consultar"),
        ("o supervisor do caixa recusou meu pagamento", "consultar"),
        # Com verbo de pedido perto, é.
        ("pásame con un supervisor", "humano"),
        ("quero falar com o gerente do banco", "humano"),
        ("comuníqueme con un ejecutivo de cuenta", "humano"),
    ],
)
def test_cargo_de_quem_atende_so_pede_humano_com_verbo_de_pedido(texto, intencao):
    assert ler(texto).intencao == intencao


@pytest.mark.parametrize(
    ("texto", "intencao"),
    [
        ("no reconozco el cobro, me robaron la tarjeta", "fraude"),
        ("não reconheço a compra, quero falar com um atendente", "humano"),
        ("quero um empréstimo pra pagar a compra", "fora_de_escopo"),
    ],
)
def test_seguranca_vence_autosservico(texto, intencao):
    assert ler(texto).intencao == intencao


@pytest.mark.parametrize(
    ("texto", "intencao"),
    [
        ("no reconozco un cobro en mi tarjeta de crédito", "contestar"),
        ("meu cartão de crédito foi recusado", "consultar"),
    ],
)
def test_cartao_de_credito_nao_e_fora_de_escopo(texto, intencao):
    assert ler(texto).intencao == intencao


@pytest.mark.parametrize(
    ("texto", "resposta"),
    [
        ("sí", "sim"),
        ("Sim, pode registrar", "sim"),
        ("claro que sí, gracias", "sim"),
        ("no", "nao"),
        ("não, obrigado", "nao"),
        ("no quiero", "nao"),
        # Nada disto confirma ou cancela: a mensagem não é só um sim ou um não.
        ("sí pero no esa", None),
        ("¿y si me rechazaron?", None),
        ("sim, mas não essa", None),
        ("sí... no", None),
        ("no reconozco", None),
    ],
)
def test_resposta_curta_so_quando_a_mensagem_inteira_responde(texto, resposta):
    assert ler(texto).resposta == resposta


@pytest.mark.parametrize(
    ("texto", "escolha"),
    [
        ("2", 2),
        ("la segunda", 2),
        ("opção 3", 3),
        ("a primeira", 1),
        ("la 2 por favor", 2),
        ("es la primera vez que me pasa", None),
        ("10", None),
        ("la segunda compra de 45,90", None),
    ],
)
def test_escolha_so_em_resposta_curta(texto, escolha):
    assert ler(texto).escolha == escolha


@pytest.mark.parametrize(
    ("texto", "valor"),
    [
        ("compra de COP 189.900,55", Decimal("189900.55")),
        ("de 45,90", Decimal("45.90")),
        ("USD 12", Decimal("12.00")),
        ("45.9", Decimal("45.90")),
        ("1.000", Decimal("1000.00")),
        ("compra de 12 el 5 de março de 2025", Decimal("12.00")),
        ("la compra del 10/03/2025", None),
        ("la compra del 5 de marzo", None),
        ("TRX-FX6", None),
        ("soy CLI-00AAKZ5VX42P", None),
    ],
)
def test_valor_nao_e_data_nem_identificador(texto, valor):
    assert ler(texto).valor == valor


@pytest.mark.parametrize(
    ("texto", "data"),
    [
        ("10/03/2025", date(2025, 3, 10)),
        ("10/03/25", date(2025, 3, 10)),
        ("01/02", date(2026, 2, 1)),
        # Sem ano e ainda por vir neste ano: é a do ano passado.
        ("25/12", date(2025, 12, 25)),
        ("el 10 de marzo", date(2025, 3, 10)),
        ("dia 5 de março de 2025", date(2025, 3, 5)),
        ("31/02/2025", None),
        ("sin fecha", None),
    ],
)
def test_data_sem_ano_nunca_no_futuro(texto, data):
    assert ler(texto).data == data


@pytest.mark.parametrize(
    ("texto", "status"),
    [
        ("¿por qué la rechazaron?", "Declined"),
        ("foi recusada", "Declined"),
        ("sigue pendiente", "Pending"),
        ("foi estornada?", "Reversed"),
        ("¿aprobada o rechazada?", None),
        ("no reconozco el cobro", None),
    ],
)
def test_status_citado_so_quando_e_um(texto, status):
    assert ler(texto).status == status


@pytest.mark.parametrize(
    ("texto", "anterior", "idioma"),
    [
        ("¿Por qué rechazaron mi compra?", "pt", "es"),
        ("Por que minha compra foi recusada?", "es", "pt"),
        ("ok", "pt", "pt"),
        ("ok", "es", "es"),
        ("não", "es", "pt"),
        ("sí", "pt", "es"),
    ],
)
def test_idioma_da_mensagem_e_empate_mantem_o_anterior(texto, anterior, idioma):
    assert ler(texto, anterior).idioma == idioma


@pytest.mark.parametrize(
    ("texto", "digitado"),
    [
        ("TRX-FX6 no la reconozco", True),
        ("soy el cliente CLI-00AAKZ5VX42P", True),
        ("soy CLI-B", True),
        ("¿cómo va el PC-00000003?", True),
        ("no reconozco la compra de 45,90", False),
        ("quiero ver el pre-caso", False),
    ],
)
def test_identificador_digitado_so_e_sinalizado(texto, digitado):
    assert ler(texto).id_digitado is digitado


def test_interpretacao_nao_carrega_identidade_nem_transacao():
    """O contrato não tem onde pôr cliente ou transação: quem identifica é a sessão, e a transação
    só sai de consulta filtrada pelo dono."""
    assert {f.name for f in fields(Interpretacao)} == {
        "idioma", "intencao", "resposta", "escolha", "valor", "data", "status", "id_digitado",
        "sinais",
    }  # fmt: skip


@pytest.mark.parametrize(
    ("comercios", "texto", "citado"),
    [
        (["Taxi Seguro", "Uber"], "no reconozco lo de uber", "Uber"),
        (["Taxi Seguro", "Uber"], "estoy seguro que no reconozco", None),
        (["Cine Premium", "Streaming Music"], "la del cine premium", "Cine Premium"),
        (["Taxi Seguro", "Uber"], "uber o taxi", None),
        (["Almacenes Éxito"], "la de exito", "Almacenes Éxito"),
        (["Farmacia Salud"], "compra na farmácia", "Farmacia Salud"),
    ],
)
def test_comercio_citado_entre_os_do_cliente(comercios, texto, citado):
    assert comercio_citado(texto, comercios) == citado
