"""Interpretação baseline (G10): cada caso tem o par que deveria dar errado — frase parecida que
não pode virar a mesma intenção, confirmação ou pista."""

import statistics
import time
from dataclasses import fields
from datetime import date
from decimal import Decimal

import pytest

from jeje.interpretacao import (
    Interpretacao,
    cartao_citado,
    cita_cartao,
    comercio_citado,
    interpretar,
)

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
        # Cobrança repetida, com o verbo de cobrar ou de aparecer perto, é contestação.
        ("me cobraron dos veces el streaming", "contestar"),
        ("a Streaming Plus me cobrou 2x no cartão", "contestar"),
        ("ya pero me aparece 2 veces", "contestar"),
        ("veio uma cobrança em dobro", "contestar"),
        ("el cargo salió duplicado", "contestar"),
        # Pedir que revisem a cobrança também.
        ("yo quiero q la revisen pq no es normal", "contestar"),
        ("quero reclamar dessa compra", "contestar"),
        # Tentar duas vezes, sem cobrança repetida, continua consulta.
        ("intenté dos veces y me rechazaron el pago", "consultar"),
        ("tentei 2 vezes pagar e foi recusado", "consultar"),
    ],
)
def test_cobranca_repetida_e_pedido_de_revisao_sao_contestacao(texto, intencao):
    assert ler(texto).intencao == intencao


@pytest.mark.parametrize(
    ("texto", "intencao"),
    [
        # ACH-120 (EV-140): pedido de contestação feito com substantivo, com valor, era consulta.
        (
            "Quiero registrar una contestación a esta compra por $30 en Farmacia Salud el 9 de"
            " marzo de 2025.",
            "contestar",
        ),
        ("Quiero abrir un reclamo por la compra de 30 dólares en Farmacia Salud", "contestar"),
        ("Necesito una objeción a la compra de 30 USD en Farmacia Salud", "contestar"),
        ("Quero registrar uma contestação da compra de 64,50 USD no Cine Premium", "contestar"),
        ("Quero abrir uma disputa da compra de 64,50 no Cine Premium", "contestar"),
        ("Quero fazer uma reclamação da cobrança de 64,50 no Cine Premium", "contestar"),
        # "Não fui eu" é relato de fraude nas duas línguas.
        ("Esa compra de 30 dólares en Farmacia Salud no la hice yo", "fraude"),
        ("Essa compra de 64,50 no Cine Premium não fui eu que fiz", "fraude"),
        # As do EV-140 que já estavam certas continuam.
        ("Quiero contestar la compra de 30 dólares en Farmacia Salud", "contestar"),
        ("Quiero disputar el cargo de 30 dólares en Farmacia Salud", "contestar"),
        ("Quiero impugnar el cobro de 30 dólares de Farmacia Salud", "contestar"),
        ("No reconozco el cargo de 30 dólares en Farmacia Salud", "contestar"),
        ("Quero contestar a compra de 64,50 dólares no Cine Premium", "contestar"),
        ("Não reconheço a compra de 64,50 dólares no Cine Premium", "contestar"),
        # Pedir estorno é consulta, por decisão (ACH-102).
        ("Quero pedir estorno da compra de 64,50 no Cine Premium", "consultar"),
    ],
)
def test_pedido_de_contestacao_com_substantivo_e_contestacao(texto, intencao):
    assert ler(texto).intencao == intencao


@pytest.mark.parametrize(
    ("texto", "intencao"),
    [
        # ACH-120 ampliado (EV-147): a transação negada como do cliente era consulta.
        ("Hay un cobro que no es mío", "contestar"),
        ("Tem uma cobrança que não é minha", "contestar"),
        ("Ese cargo no es mío", "contestar"),
        ("Essa compra não é minha", "contestar"),
        ("Hay un cobro de 30 dólares que no es mío", "contestar"),
        ("Tem uma cobrança de 64,50 que não é minha", "contestar"),
        # Sem a transação perto, nada muda.
        ("¿Por qué rechazaron mi pago? Ese error no es mío", "consultar"),
    ],
)
def test_transacao_que_nao_e_do_cliente_e_contestacao(texto, intencao):
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
        # Recusar o atendente não é pedir um.
        ("Pero no quiero un agente, solo dime cuál fue la de mayor monto", "desconhecida"),
        ("não quero falar com atendente, quero ver a compra da Uber", "consultar"),
        ("sin agente por favor", "desconhecida"),
        # Pedido, com negação de outra coisa, continua pedido.
        ("no entiendo nada, quiero hablar con un agente", "humano"),
        ("no quiero esperar, quiero un agente", "humano"),
    ],
)
def test_recusar_o_atendente_nao_e_pedir_um(texto, intencao):
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
        ("quero a primeira", 1),
        ("fue la segunda", 2),
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
        # Escolha curta não é valor.
        ("A 1", None),
        ("la 2 por favor", None),
        # Contagem não é valor.
        ("me aparece 2 veces", None),
        ("pq salen 2 cobros? son de 45,90", Decimal("45.90")),
        ("caiu 2 vezes", None),
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
        "idioma", "intencao", "resposta", "aceita_oferta", "escolha", "valor", "data", "status",
        "id_digitado", "caso", "ultima", "cortesia", "sinais",
    }  # fmt: skip


@pytest.mark.parametrize(
    ("texto", "cortesia"),
    [
        ("okay, obrigado", "agradecimento"),
        ("muchas gracias, muy amable", "agradecimento"),
        ("perfeito, obrigada pela ajuda", "agradecimento"),
        ("era isso, tchau", "agradecimento"),
        ("no, gracias", "agradecimento"),
        ("oi, tudo bem?", "saudacao"),
        ("hola, buenas tardes", "saudacao"),
        # Com pedido junto, é o pedido que vale.
        ("obrigado, e a outra transação?", None),
        ("hola, quiero saber por qué rechazaron mi compra", None),
        ("gracias por nada, sigo sin mi dinero", None),
        ("", None),
    ],
)
def test_cortesia_so_quando_a_mensagem_inteira_e_cumprimento_ou_agradecimento(texto, cortesia):
    assert ler(texto).cortesia == cortesia


@pytest.mark.parametrize(
    "texto",
    [
        # ACH-128 (DEV-062): a negação antes do fechamento é insatisfação, não agradecimento.
        "no resolvió", "no entendí", "no era eso", "no, no era eso", "no ok", "não resolveu",
        "não entendi", "não era isso", "não é isso", "não, não resolveu", "todavía no resolvió",
        "ainda não resolveu",
    ],
)  # fmt: skip
def test_negacao_antes_do_fechamento_nao_e_cortesia(texto):
    assert ler(texto).cortesia is None


@pytest.mark.parametrize(
    "texto",
    ["no, gracias", "não, obrigado", "listo, gracias", "resolveu, valeu", "gracias", "obrigado"],
)
def test_agradecimento_com_ou_sem_negacao_continua_cortesia(texto):
    assert ler(texto).cortesia == "agradecimento"


@pytest.mark.parametrize(
    ("texto", "ultima"),
    [
        ("quero saber pq minha ultima transacao foi recusada", True),
        ("¿por qué rechazaron mi último pago?", True),
        ("a compra mais recente", True),
        ("la última", True),
        # Tempo, não a transação; e o plural pede várias.
        ("la última vez que intenté me rechazaron", False),
        ("no último mês me cobraram duas vezes", False),
        ("quero ver minhas últimas transações", False),
    ],
)
def test_ultima_e_a_mais_recente_e_nao_a_ultima_vez(texto, ultima):
    assert ler(texto).ultima is ultima


@pytest.mark.parametrize(
    ("texto", "caso"),
    [
        ("¿Cómo va mi solicitud de revisión?", True),
        ("como está o meu pedido de revisão?", True),
        ("¿qué pasó con mi reclamo?", True),
        ("quero ver meus pedidos de revisão", True),
        ("quiero ver el pre-caso", True),
        ("cadê o protocolo?", True),
        ("¿cómo va el PC-00000003?", True),
        # Pedir uma revisão nova é contestação, não pergunta pela registrada.
        ("quiero abrir una disputa", False),
        ("quero fazer um pedido de revisão", False),
        ("no reconozco el cobro de 45,90, que lo revisen", False),
        ("en mi caso la compra fue rechazada", False),
        ("quiero una solicitud de préstamo", False),
    ],
)
def test_pergunta_pelo_pedido_registrado_so_com_possessivo_andamento_ou_protocolo(texto, caso):
    assert ler(texto).caso is caso


FX = ["Café Central", "Streaming Plus", "Boutique Moda", "Óptica Visión", "Uber", "Ferretería",
      "Cine Premium", 'Viajes "El Cóndor", S.A.', "Almacenes Éxito", "Farmacia Salud"]  # fmt: skip


@pytest.mark.parametrize(
    ("comercios", "texto", "citado"),
    [
        (["Taxi Seguro", "Uber"], "no reconozco lo de uber", "Uber"),
        (["Taxi Seguro", "Uber"], "estoy seguro que no reconozco", None),
        (["Cine Premium", "Streaming Music"], "la del cine premium", "Cine Premium"),
        (["Taxi Seguro", "Uber"], "uber o taxi", None),
        (["Almacenes Éxito"], "la de exito", "Almacenes Éxito"),
        (["Farmacia Salud"], "compra na farmácia", "Farmacia Salud"),
        # O ramo que o nome diz, como o cliente fala dele.
        (FX, "foi numa ótica acho, deu ruim na hora de pagar", "Óptica Visión"),
        (FX, "eu disse que foi loja de roupa!", "Boutique Moda"),
        (FX, "los pasajes de avión", 'Viajes "El Cóndor", S.A.'),
        (FX, "a compra da viagem", 'Viajes "El Cóndor", S.A.'),
        (FX, "la de las herramientas", "Ferretería"),
        (FX, "comprei remédio", "Farmacia Salud"),
        (FX, "o cafezinho de 12", "Café Central"),
        (FX, "la película", "Cine Premium"),
        (["Mercado Central", "Super Ahorro"], "fue en el supermercado", None),  # dois ramos iguais
        # Mensagens sem comércio continuam sem.
        (FX, "no sé, fue en una tienda, creo que fue caro", None),
        (FX, "e agora o que eu faço", None),
        (FX, "me cobraron dos veces", None),
    ],
)
def test_comercio_citado_entre_os_do_cliente(comercios, texto, citado):
    assert comercio_citado(texto, comercios) == citado


# ---- Bloqueio de cartão (PRD-007) ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "intencao"),
    [
        ("quiero bloquear mi tarjeta", "bloquear"),
        ("bloqueen la tarjeta terminada en 9241, por favor", "bloquear"),
        ("¿cómo bloqueo mi tarjeta de débito?", "bloquear"),
        ("quero bloquear o meu cartão", "bloquear"),
        ("bloqueia meu cartão de crédito", "bloquear"),
        # A vírgula separa a negação do pedido: "no" responde outra coisa.
        ("no, bloqueen mi tarjeta", "bloquear"),
        ("quiero desbloquear mi tarjeta", "desbloquear"),
        ("desbloqueia meu cartão", "desbloquear"),
    ],
)
def test_pedido_de_bloqueio_ou_desbloqueio_com_verbo_de_pedido_perto_de_cartao(texto, intencao):
    assert ler(texto).intencao == intencao


@pytest.mark.parametrize(
    "texto",
    [
        "¿por qué bloquearon mi tarjeta?",  # pergunta pelo motivo
        "mi tarjeta está bloqueada",  # estado
        "meu cartão foi bloqueado?",
        "no quiero bloquear mi tarjeta",  # negação
        "não bloqueie meu cartão",
        "no la bloqueen, solo quiero saber por qué rechazaron la compra",
        "não quero desbloquear o cartão",
        "quiero bloquear mi cuenta",  # não é cartão
    ],
)
def test_pergunta_estado_negacao_ou_sem_cartao_nao_sao_pedido_de_bloqueio(texto):
    assert ler(texto).intencao not in ("bloquear", "desbloquear")


@pytest.mark.parametrize(
    ("texto", "intencao"),
    [
        # REG-06 (ACH-140): as palavras comuns de cada pedido, com a intenção do controle.
        ("Congela mi tarjeta, por favor", "bloquear"),
        ("Quiero congelar mi tarjeta", "bloquear"),
        ("Quero travar o cartão", "bloquear"),
        ("Trava meu cartão, por favor", "bloquear"),
        ("Reactiva mi tarjeta", "desbloquear"),
        ("Ya apareció mi tarjeta, quiero usarla", "desbloquear"),
        ("Quero reativar o cartão", "desbloquear"),
        ("Pode liberar meu cartão de novo", "desbloquear"),
        ("No quiero hablar con un robot", "humano"),
        ("Não quero falar com robô", "humano"),
        ("Me están robando plata de la cuenta", "fraude"),
        ("Caí num golpe e fizeram um pix", "fraude"),
        ("Estão tirando dinheiro da minha conta", "fraude"),
    ],
)
def test_palavras_comuns_do_cartao_do_atendente_e_da_fraude(texto, intencao):
    assert ler(texto).intencao == intencao


@pytest.mark.parametrize(
    "texto",
    [
        "¿Por qué está congelada mi tarjeta?",  # estado, não pedido
        "Meu cartão travou na maquininha",
        "no quiero congelar mi tarjeta",  # negação
        "não quero travar o cartão",
        "Quiero activar mi tarjeta nueva",  # ativar o cartão novo não é desbloqueio
        "Apareció un cobro en mi tarjeta que no reconozco",
        "Encontré un pago con tarjeta no autorizado",  # o cartão não é o achado
    ],
)
def test_estado_negacao_e_cartao_novo_nao_viram_pedido_de_bloqueio(texto):
    assert ler(texto).intencao not in ("bloquear", "desbloquear")


@pytest.mark.parametrize(
    "texto",
    [
        # ACH-141: o bloqueio que o cliente fez é contexto; o pedido é a volta.
        "Ya bloqueé mi tarjeta, ahora quiero desbloquearla",
        "Bloqueé mi tarjeta por error, ¿me la pueden desbloquear?",
        "Mi tarjeta está bloqueada, quiero usarla de nuevo",
        "Meu cartão está bloqueado, quero liberar",
        # O pedido longe do cartão ou do bloqueio, depois de contar o que houve.
        "Bloquee mi tarjeta ayer sin querer y ahora no puedo pagar el supermercado, ¿me la pueden "
        "desbloquear?",
        "La bloqueé por error, ¿me la pueden desbloquear?",
        "Acabei de bloquear meu cartão sem querer e agora não pago a luz, dá para reativar?",
        "Eu bloqueei o cartão e não consigo comprar nada, como faço para liberar?",
    ],
)
def test_pedido_de_volta_com_o_bloqueio_contado_e_desbloqueio(texto):
    assert ler(texto).intencao == "desbloquear"


@pytest.mark.parametrize(
    "texto",
    [
        # O PIN não é o cartão, e o cartão encerrado não foi bloqueado pelo cliente.
        "Dado que mi PIN está bloqueado, ¿me ayudarías a desbloquearlo?",
        "Meu cartão de débito foi encerrado e perdi a senha, como faço para reativá-lo?",
        "Mi tarjeta está bloqueada y no quiero liberarla todavía",  # negado
    ],
)
def test_pin_cartao_encerrado_e_volta_negada_nao_sao_desbloqueio(texto):
    assert ler(texto).intencao != "desbloquear"


def test_bloqueio_contado_nao_pede_outro_bloqueio():
    """ACH-141: "bloqueé" (com acento) e "ya/la/lo/me bloquee" contam o que o cliente já fez; o
    imperativo e o "que" antes continuam pedido."""
    assert ler("Ya bloqueé mi tarjeta, ¿y ahora qué hago?").intencao != "bloquear"
    assert ler("Ya bloquee mi tarjeta, ¿y ahora qué hago?").intencao != "bloquear"
    assert ler("Bloquee mi tarjeta, por favor").intencao == "bloquear"
    assert ler("Mi tarjeta, necesito que la bloquee ya").intencao == "bloquear"
    assert ler("Le pido que me la bloquee: es mi tarjeta").intencao == "bloquear"


@pytest.mark.parametrize(
    "texto",
    [
        # ACH-142: o golpe de engenharia social contado como história é relato de fraude.
        "Un hombre que dijo ser funcionario del banco me pidió una transferencia",
        "Um homem se passou por funcionário do banco e eu acreditei",
        "Me escribió alguien que me dijo que era mi primo y le mandé plata",
        "Recebi mensagem de alguém que disse que era meu sobrinho",
        "Hablé con un supuesto asesor por teléfono y ahora tengo cargos",
        "Uma falsa central me ligou ontem",
        "Passei a senha do cartão para um desconhecido no telefone",
        "Le di la clave a una persona que me llamó",
        "Entré a una página falsa del banco y puse mis datos",
        "Cliquei num link falso que chegou por SMS",
        "Están pidiendo dinero a mis contactos con mi nombre",
        "Alguém está pedindo dinheiro aos meus contatos no meu nome",
        "Aparecieron transferencias que no hice en mi cuenta",
        "Saíram transferências da minha conta sem minha autorização",
        "Hay compras en mi cuenta y no sé quién las hizo",
        "Creo que fue phishing",
        "Le transferí a un estafador",
        "Fiz um pix para um golpista",
        "Creo que fue un timo",
        "Acho que foi trapaça",
        "Mi WhatsApp fue hackeado",
        "Alguém hackeou minha conta",
        "Sufrí un hackeo",
        "Alguém clonou meu WhatsApp",
        "Hubo una usurpación de mi identidad",
        "Fui enganado numa venda pela internet",
        "Me engañaron con un premio",
        "Mis datos fueron robados",
        "Meus dados foram roubados",
        "Entrei no site errado e digitei tudo",
    ],
)
def test_golpe_de_engenharia_social_e_relato_de_fraude(texto):
    assert ler(texto).intencao == "fraude"


@pytest.mark.parametrize(
    ("texto", "intencao"),
    [
        # "Disse que era" sem quem ele disse ser logo depois; "entregue" é o PT de entregar.
        ("O vendedor disse que era problema do banco", "desconhecida"),
        ("O PIN é entregue separadamente?", "desconhecida"),
        ("Há algo de errado com o seu site?", "desconhecida"),
        ("Bloqueei meu cartão por engano", "desconhecida"),  # engano é erro, não golpe
        # O estranho hipotético e a compra não feita continuam o que eram.
        ("No quiero problemas con movimientos extraños, quiero bloquear mi tarjeta", "bloquear"),
        ("Me cobraron una compra que no hice", "contestar"),
    ],
)
def test_palavras_perto_do_golpe_nao_viram_relato_de_fraude(texto, intencao):
    assert ler(texto).intencao == intencao


def test_queixa_de_tarifa_com_robando_nao_e_relato_de_fraude():
    """Sem o dinheiro ou a conta perto, "robando" é queixa, não relato (visto no BANKING77)."""
    assert ler("Más comisiones otra vez. ¿Por qué me estás robando así?").intencao != "fraude"


def test_roubo_e_perda_com_pedido_de_bloqueio_continuam_relato_de_fraude():
    """Segurança primeiro: o relato encaminha (e, na conversa, também bloqueia)."""
    assert ler("me robaron la tarjeta, bloquéenla").intencao == "fraude"
    assert ler("perdi meu cartão, quero bloquear").intencao == "fraude"


CARTOES = [("Tarjeta Crédito", "9241"), ("Tarjeta Débito", "5678"), ("Tarjeta Crédito", None)]


@pytest.mark.parametrize(
    ("cartoes", "texto", "citado"),
    [
        (CARTOES, "la terminada en 9241", 0),
        (CARTOES, "o de final 5678", 1),
        (CARTOES, "la de débito", 1),
        (CARTOES[:2], "la de crédito", 0),
        (CARTOES, "la de crédito", None),  # dois de crédito: quem escolhe é o cliente
        (CARTOES, "la de 9241 o la de 5678", None),  # dois citados
        (CARTOES, "la de débito terminada en 9241", None),  # final e tipo não batem
        (CARTOES, "4000000000009241", None),  # número inteiro não é final
        (CARTOES, "la terminada en 1234", None),  # final de nenhum cartão do cliente
        (CARTOES[:1], "esa", None),  # nada citado não escolhe nem o único
    ],
)
def test_cartao_citado_pelo_final_ou_pelo_tipo_entre_os_do_cliente(cartoes, texto, citado):
    assert cartao_citado(texto, cartoes) == citado


@pytest.mark.parametrize(
    ("texto", "cita"),
    [
        ("bloqueen la terminada en 1234", True),  # final, case ou não com um cartão do cliente
        ("quiero bloquear mi tarjeta de crédito", True),  # tipo
        ("o de débito", True),
        ("quiero bloquear mi tarjeta", False),
        ("me robaron la tarjeta", False),
        ("4000000000009241", False),  # número inteiro não é final
    ],
)
def test_cita_cartao_quando_diz_final_ou_tipo(texto, cita):
    assert cita_cartao(texto) is cita


def test_ler_uma_mensagem_custa_poucos_milissegundos():
    """ACH-107: cada mensagem passa por mais termos do que o cache do `re` guarda (512); com as
    expressões recompiladas a cada chamada, a leitura levava ~100 ms. Compiladas uma vez, ficava
    perto de 2 ms; com os termos do golpe (ACH-142), testar os pares um a um levou a ~6 ms. Com
    todos os pares de cada composto numa expressão só, fica perto de 1 ms; o limite de 3 ms deixa
    folga para a máquina carregada. Vale para cada frase, inclusive a que casa o último par de um
    composto grande, que compila centenas de pares na primeira vez."""
    frases = [
        "¿Por qué me rechazaron la compra de 45,90 del 10/03?",
        "No reconozco el cobro de Uber",
        "Quiero bloquear mi tarjeta",
        "hola, buenas tardes",
        "me robaron la tarjeta",
        "não quero desbloquear meu cartão",
        "Una mujer fingiendo ser mi amiga me pidió plata",
    ]
    for frase in frases:  # a primeira leitura compila; o que importa é o regime
        interpretar(frase, "es", REFERENCIA)
    tempos: dict[str, list[float]] = {frase: [] for frase in frases}
    for _ in range(10):
        for frase in frases:
            inicio = time.perf_counter()
            interpretar(frase, "es", REFERENCIA)
            tempos[frase].append((time.perf_counter() - inicio) * 1000)
    assert max(statistics.median(t) for t in tempos.values()) <= 3


@pytest.mark.parametrize(
    "texto",
    [
        "Essa transação é fraudulenta",
        "A compra de 19,99 na Uber é fraudulenta",
        "Esta transacción es fraudulenta",
        "La compra de 30 dólares en Farmacia Salud es fraudulenta",
    ],
)
def test_dizer_que_a_compra_e_fraudulenta_e_relato_de_fraude(texto):
    """ACH-121 (DEV-020r): o adjetivo também relata fraude, que vai ao atendente (POL-HUM-01)."""
    assert ler(texto).intencao == "fraude"


@pytest.mark.parametrize(
    ("texto", "valor"),
    [
        ("No reconozco el cobro de 6,050", Decimal("6050.00")),
        ("No reconozco el cobro de 6,050.00", Decimal("6050.00")),
        ("No reconozco el cobro de USD13,45", Decimal("13.45")),
        ("Não reconheço a cobrança de usd13.45", Decimal("13.45")),
        ("No reconozco el cobro de 13,45", Decimal("13.45")),
        ("No reconozco el cobro de 1,5", Decimal("1.50")),
        ("No reconozco el cobro de COP 189.900,55", Decimal("189900.55")),
        ("No reconozco el cobro de 45.90", Decimal("45.90")),
    ],
)
def test_valor_no_formato_do_mexico_e_dos_eua_e_com_o_codigo_colado(texto, valor):
    """DEV-043 (EXP-007): vírgula seguida de exatamente 3 dígitos é milhar ("6,050" e "6,050.00"),
    o código da moeda colado ao número não impede a leitura, e o decimal com vírgula ou ponto
    continua ("13,45", "1,5", "45.90")."""
    assert ler(texto).valor == valor


@pytest.mark.parametrize(
    ("texto", "valor"),
    [
        # REG-05 (ACH-129): o número com cara de dinheiro, não o primeiro número da frase.
        ("En mi tarjeta terminada en 6604 hay un cargo de 45,90 dólares que no reconozco",
         Decimal("45.90")),
        ("A las 3 de la tarde me cobraron 50 dólares y no lo reconozco", Decimal("50.00")),
        ("El día 15 me cobraron 45,90 USD y no lo reconozco", Decimal("45.90")),
        ("No cartão final 6604 tem uma cobrança de 45,90 dólares que não reconheço",
         Decimal("45.90")),
        ("Às 3 da tarde me cobraram 50 reais e não reconheço", Decimal("50.00")),
        ("No dia 15 me cobraram 45,90 USD e não reconheço", Decimal("45.90")),
        ("a las 10:30 me cobraron 20 dólares", Decimal("20.00")),
        ("às 15h me cobraram 20 reais", Decimal("20.00")),
        # A hora sem "a las" ou "às", e sem dinheiro marcado: o valor é o outro número.
        ("el cargo de las 10:30 fue de 45,90", Decimal("45.90")),
        ("el cobro de las 15 hs fue de 45,90", Decimal("45.90")),
        # REG-04 (ACH-127): o tempo antes ou depois do valor não é valor.
        ("Hace 3 días me cobraron 45 dólares que no reconozco", Decimal("45.00")),
        ("No reconozco el cargo de 45 dólares de hace 2 días", Decimal("45.00")),
        ("Faz 2 semanas que me cobraram 45 reais e não reconheço", Decimal("45.00")),
        ("Não reconheço a cobrança de 45 reais de 2 dias atrás", Decimal("45.00")),
        # Sem dinheiro na frase, nenhum desses números é valor.
        ("tarjeta terminada en 6604", None),
        ("Faz 4 dias que uma compra está pendente", None),
        ("el día 15", None),
        ("llamé al 018000", None),
        ("lo pagué en 3 cuotas", None),
        ("mi cuenta 123456 tiene un cobro de 45,90", Decimal("45.90")),
        # Com dois números, vale o marcado como dinheiro.
        ("me devolvieron 2 compras de 45,90 dólares", Decimal("45.90")),
        ("fue a las 10:30", None),
        ("lo vi a las 3", None),
        # A conta citada sem número não leva o valor junto (visto no BANKING77).
        ("un retiro de mi cuenta por 500 libras que no hice", Decimal("500.00")),
        # "N mil" é N vezes mil.
        ("me cobraron 30 mil pesos", Decimal("30000.00")),
    ],
)  # fmt: skip
def test_valor_e_o_numero_com_cara_de_dinheiro(texto, valor):
    assert ler(texto).valor == valor


@pytest.mark.parametrize(
    ("texto", "data"),
    [
        # O dia do mês sem o mês: o mais recente até a referência (01/03/2026).
        ("El día 15 me cobraron 45,90 USD", date(2026, 2, 15)),
        ("No dia 1 me cobraram 20 reais", date(2026, 3, 1)),
        # O mês abreviado.
        ("la compra del 15 de mar", date(2025, 3, 15)),
        ("a compra de 3 de fev", date(2026, 2, 3)),
    ],
)
def test_dia_do_mes_e_mes_abreviado_viram_data(texto, data):
    assert ler(texto).data == data


@pytest.mark.parametrize(
    "texto",
    [
        "sí, pásame", "sí, por favor, comunícame", "sí, adelante", "bueno", "por favor", "obvio",
        "afirmativo", "sip", "va", "pode passar", "sim, pode passar", "pode ser", "com certeza",
        "isso mesmo", "beleza", "uhum", "quero", "simm",
    ],
)  # fmt: skip
def test_aceites_comuns_aceitam_a_oferta_mas_nao_confirmam_acao(texto):
    """ACH-123 (DEV-020t): depois da oferta do atendente (sem efeito financeiro), o aceite é mais
    largo; o sim que confirma pré-caso ou desbloqueio continua estrito."""
    lida = ler(texto)
    assert (lida.aceita_oferta, lida.resposta) == (True, None)


@pytest.mark.parametrize(
    "texto", ["no", "não quero", "sí, pero no esa", "¿y si me rechazaron?", "por favor, no"]
)
def test_negar_ou_perguntar_nao_aceita_a_oferta(texto):
    assert ler(texto).aceita_oferta is False
