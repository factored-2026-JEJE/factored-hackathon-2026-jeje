"""Interpretação baseline (G10): cada caso tem o par que deveria dar errado — frase parecida que
não pode virar a mesma intenção, confirmação ou pista."""

import statistics
import time
from dataclasses import fields
from datetime import date
from decimal import Decimal

import pytest

from jeje import interpretacao
from jeje.interpretacao import (
    Interpretacao,
    cartao_citado,
    cita_cartao,
    comercio_citado,
    comercio_citado_e_como,
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
        "idioma", "intencao", "resposta", "aceita_oferta", "outra", "escolha", "valor",
        "valor_marcado", "data", "status", "id_digitado", "caso", "ultima", "cortesia", "sinais",
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
        # ACH-150 (a regra medida no QT-03): as palavras comuns do nome não citam o comércio
        # sozinhas, e o telefone deixa de ser o ramo da Empresa Telefónica; o nome inteiro cita.
        (["Internet Plus"], "lo compré por internet", None),
        (["Internet Plus"], "paguei pela internet", None),
        (["Empresa Telefónica"], "me llamaron por teléfono", None),
        (["Empresa Telefónica"], "recibí una llamada telefónica", None),
        (["Empresa Telefónica"], "falei pelo telefone", None),
        (["Restaurante El Buen Sabor"], "Buen día, no reconozco un cobro", None),
        (["Tienda Don José"], "Hola, soy José", None),
        (["Super Ahorro"], "salió de mi cuenta de ahorro", None),
        (["Farmacia Salud"], "lo necesito por mi salud", None),
        (["Internet Plus"], "el cobro de Internet Plus", "Internet Plus"),
        (["Tienda Don José"], "compré en la Tienda Don José", "Tienda Don José"),
        (["Super Ahorro"], "foi na Super Ahorro", "Super Ahorro"),
        (["Restaurante El Buen Sabor"], "la cena en El Buen Sabor", "Restaurante El Buen Sabor"),
        # Mensagens sem comércio continuam sem.
        (FX, "no sé, fue en una tienda, creo que fue caro", None),
        (FX, "e agora o que eu faço", None),
        (FX, "me cobraron dos veces", None),
    ],
)
def test_comercio_citado_entre_os_do_cliente(comercios, texto, citado):
    assert comercio_citado(texto, comercios) == citado


def test_comercio_citado_diz_se_veio_do_nome_inteiro_ou_de_uma_palavra():
    """O DEV-072 trata diferente a palavra solta (que perde para o valor exato) e o nome inteiro."""
    assert comercio_citado_e_como("lo de Streaming Plus", FX) == ("Streaming Plus", "nome")
    assert comercio_citado_e_como("lo de streaming", FX) == ("Streaming Plus", "palavra")
    assert comercio_citado_e_como("la película", FX) == ("Cine Premium", "palavra")
    assert comercio_citado_e_como("nada", FX) == (None, None)


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
        ("Trava o cartão, por favor", "bloquear"),
        ("Congela la tarjeta de débito", "bloquear"),
        ("Reactiva mi tarjeta", "desbloquear"),
        ("Ya apareció mi tarjeta, quiero usarla", "desbloquear"),
        ("Quero reativar o cartão", "desbloquear"),
        ("Pode liberar meu cartão de novo", "desbloquear"),
        ("No quiero hablar con un robot", "humano"),
        ("Não quero falar com robô", "humano"),
        ("Me están robando plata de la cuenta", "fraude"),
        ("Caí num golpe e fizeram um pix", "fraude"),
        ("Estão tirando dinheiro da minha conta", "fraude"),
        # REG-21: a conta esvaziada.
        ("Me vaciaron la cuenta", "fraude"),
        ("Entraron a mi cuenta y la vaciaron", "fraude"),
        ("Me pidieron el código por WhatsApp, lo di y vaciaron mi cuenta", "fraude"),
        ("Esvaziaram minha conta", "fraude"),
        ("Passei o código e limparam minha conta", "fraude"),
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
        # "Trava" e "congela" descrevendo o cartão ou o app (auditoria do dev, 02/10).
        "Meu cartão trava na maquininha",
        "Mi tarjeta se congela cuando pago con el celular",
        "A trava do cartão foi ativada sozinha",
        "O aplicativo trava quando abro o cartão",
        "Por que o cartão trava em compras online?",
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
    perto de 2 ms; com os termos do golpe (ACH-142), testar todos os pares levou a ~8 ms. Testando
    só os pares com os dois termos na mensagem, fica perto de 1 ms (2,5 ms com a máquina
    carregada); o limite de 5 ms vale para cada frase, inclusive a que casa o último par de um
    composto grande."""
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
    assert max(statistics.median(t) for t in tempos.values()) <= 5


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
        ("No reconozco el cobro de 1 000 dólares", Decimal("1000.00")),
        ("Não reconheço a cobrança de 100 000 pesos", Decimal("100000.00")),
        ("No reconozco el cobro de 3 400 000 pesos", Decimal("3400000.00")),
        ("No reconozco el cobro de 25 000 pesos", Decimal("25000.00")),
    ],
)
def test_valor_com_milhar_separado_por_espaco(texto, valor):
    """ACH-155: o grupo de milhar depois do espaço ("1 000") não é um código com zero à esquerda."""
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
    ("texto", "marcado"),
    [
        # ACH-143: o número solto pode ser o dia ou o final do cartão; moeda, símbolo ou centavos
        # dizem que é dinheiro.
        ("me cobraron 46", False),
        ("me cobraron unos 46", False),
        ("me cobraron 46 dólares", True),
        ("me cobraron USD 46", True),
        ("me cobraram R$ 46", True),
        ("me cobraron 45,90", True),
        ("me cobraron 45.90", True),
    ],
)
def test_valor_marcado_tem_moeda_simbolo_ou_centavos(texto, marcado):
    assert ler(texto).valor_marcado is marcado


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
    ("texto", "outra"),
    [
        # ACH-145: a recusa da transação apontada, não do pedido.
        ("No, esa no", True),
        ("Não, essa não", True),
        ("no es esa", True),
        ("não é essa", True),
        ("esa no es", True),
        ("Não, outra", True),
        ("la otra", True),
        # O "não" sozinho e a correção com pista seguem como antes.
        ("no", False),
        ("sí", False),
        ("No, era el de 64,50 USD", False),
        ("e a outra transação?", False),
    ],
)
def test_recusa_da_transacao_apontada(texto, outra):
    assert ler(texto).outra is outra


@pytest.mark.parametrize(
    "texto", ["no", "não quero", "sí, pero no esa", "¿y si me rechazaron?", "por favor, no"]
)
def test_negar_ou_perguntar_nao_aceita_a_oferta(texto):
    assert ler(texto).aceita_oferta is False


@pytest.mark.parametrize(
    ("texto", "prevencao"),
    [
        ("¿Cómo puedo evitar caer en una estafa?", True),
        ("Quero dicas para não cair em golpe", True),
        ("Recibí un mensaje raro, no di mis datos, ¿es una estafa?", True),
        ("Me ligaram dizendo ser do banco, não passei nada, era golpe?", True),
        ("Me escribieron del banco y no le di mis datos, ¿era una estafa?", True),  # "no le di"
        # REG-21: o objeto antes do verbo ("no se la di") e o nada entregue.
        (
            "Me llamaron diciendo que eran del banco y me pidieron la clave. "
            "No se la di, ¿es normal?",
            True,
        ),
        ("Me escribieron por WhatsApp pidiendo el código, pero no se lo di", True),
        ("Me llegó un SMS pidiendo mis datos; no se los di", True),
        ("Um suposto atendente pediu o código e eu não informei", True),
        # Termo de vítima não negado: é relato, mesmo com a palavra de prevenção.
        ("Fui vítima de golpe, como me protejo agora?", False),
        ("Me estafaron, transferí 500 dólares", False),
        ("Caí en una estafa y me sacaron dinero", False),
        ("Me robaron la tarjeta", False),
        # A conta esvaziada é perda, mesmo com a suspeita na mesma mensagem (REG-21).
        ("Un supuesto asesor me pidió la clave, no se la di, pero igual vaciaron mi cuenta", False),
        ("Um falso atendente pediu o código, não informei, mas esvaziaram minha conta", False),
    ],
)
def test_prevencao_ou_suspeita_sem_perda_nao_e_relato_de_vitima(texto, prevencao):
    """ACH-144 (NOV-35 da validação): a pergunta de prevenção ou a suspeita sem perda, sem termo
    de vítima não negado, não é relato de quem perdeu o cartão ou o dinheiro."""
    assert interpretacao.prevencao(texto) == prevencao


@pytest.mark.parametrize(
    ("texto", "intencao"),
    [
        # DEV-060 (NOV-24): a palavra de intenção com uma letra errada conta como a certa.
        ("No reconosco un cargo de 45,90", "contestar"),
        ("Nao reconheso uma cobransa de 45,90", "contestar"),
        ("me robron la tarjeta", "fraude"),
        ("quiero hablar con un atenente", "humano"),
        # Palavra do vocabulário, curta ou longe de um termo não muda a leitura.
        ("He probado la app y no funciona", "desconhecida"),
        ("Quiero contratar un seguro", "desconhecida"),
        ("meu cartão pessoal foi recusado", "consultar"),
        ("¿estoy hablando con un robot?", "desconhecida"),
        ("A loja precisa de um gerente novo", "desconhecida"),  # "precisa" não vira "preciso"
    ],
)
def test_erro_de_digitacao_na_palavra_de_intencao(texto, intencao):
    assert ler(texto).intencao == intencao


def test_termo_com_uma_letra_a_mais_no_fim_nao_e_erro_de_digitacao():
    """O termo com uma letra a mais no fim é outra palavra: "pessoal" não é "pessoa" digitado errado
    (ACH-172), nem "golpes" é "golpe" (REG-14)."""
    assert not interpretacao._uma_edicao("pessoal", "pessoa")
    assert not interpretacao._uma_edicao("personal", "persona")
    assert not interpretacao._uma_edicao("golpes", "golpe")
    assert interpretacao._uma_edicao("robron", "robaron")
    assert interpretacao._uma_edicao("pesoa", "pessoa")


def test_palavra_com_menos_de_6_letras_nao_e_corrigida():
    """Corrigir palavra curta troca demais (NOV-23): "golfe" não vira "golpe"."""
    texto = "paguei a aula de golfe com o cartão"
    assert interpretacao.corrigir(texto) == (texto, ())


def test_a_correcao_de_digitacao_fica_nos_sinais():
    assert ler("me robron la tarjeta").sinais[-1] == "digitacao:robron→robaron"


def test_vocabulario_versionado_tem_palavras_normalizadas_com_a_contagem():
    linhas = interpretacao.VOCABULARIO_DO_ARQUIVO.read_text(encoding="utf-8").splitlines()
    pares = [linha.split("\t") for linha in linhas]
    assert [p for p, _ in pares] == sorted({p for p, _ in pares})
    assert all(interpretacao.normalizar(p) == p and int(n) >= 1 for p, n in pares)
    assert interpretacao.VOCABULARIO["reconozco"] >= 2 and interpretacao.VOCABULARIO["probado"] == 1


@pytest.mark.parametrize(
    "texto",
    [
        # DEV-079 (ACH-157, PERDA-01): as outras formas de dizer que o cartão foi perdido ou levado.
        "Me quitaron la tarjeta en el metro",
        "Me hurtaron la cartera con las tarjetas",
        "No hallo mi tarjeta por ningún lado",
        "No puedo encontrar mi tarjeta, se ha ido",
        "Ya no tengo mi tarjeta",
        "Olvidé la tarjeta en un taxi",
        "Se me cayó la tarjeta y no aparece",
        "Se me perdió la tarjeta ayer",
        "Furtaram meu cartão no ônibus",
        "Levaram minha carteira com o cartão",
        "Não acho meu cartão",
        "Não consigo achar o cartão",
        "Não tenho mais o cartão",
        "Meu cartão desapareceu",
        "Meu cartão caiu e não acho",
        "Esqueci o cartão no táxi",
        # Com o cartão antes do verbo e nada antes dele que mostre outro objeto (ACH-190).
        "Mi tarjeta no aparece por ningún lado",
        "Hace dos días que mi tarjeta no aparece",
        # Com o verbo antes do cartão, o que vem antes do verbo não conta.
        "Hice una compra y perdí la tarjeta",
        # O cartão antes do verbo, com o tipo do cartão ou "se me cayó" no meio (EV-199).
        "Mi tarjeta de crédito se me perdió",
        "Mi tarjeta se me cayó y no aparece",
        "Meu cartão de crédito caiu e não acho",
        "Mi tarjeta de débito se me cayó en la calle",
    ],
)
def test_perda_ou_roubo_do_cartao_dito_de_outras_formas_e_fraude(texto):
    assert ler(texto).intencao == "fraude"


@pytest.mark.parametrize(
    ("texto", "intencao"),
    [
        # Os mesmos verbos sem o cartão perto não são relato de perda.
        ("No puedo encontrar la compra en mi historial", "consultar"),
        ("Já não tenho dúvidas sobre a cobrança", "consultar"),
        ("Olvidé mi contraseña", "fora_de_escopo"),
        ("Esqueci a senha do app", "fora_de_escopo"),
        ("Não acho essa compra no extrato do cartão", "consultar"),
        ("Ya no tengo saldo en la cuenta", "desconhecida"),
        # Com o cartão perto, mas o objeto é outro (a senha, a compra, o limite): não é perda.
        ("Esqueci a senha do cartão", "fora_de_escopo"),
        ("La compra no aparece en la tarjeta", "consultar"),
        ("Não acho a compra no cartão", "consultar"),
        ("Não encontro a compra no cartão", "consultar"),
        ("Ya no tengo saldo en la tarjeta", "desconhecida"),
        ("perdi o prazo do cartão", "desconhecida"),
        ("En la tarjeta la compra no aparece", "consultar"),  # o cartão antes do verbo
        # O cartão antes do verbo, mas como complemento da compra ou do cargo (ACH-190).
        ("La compra con mi tarjeta no aparece", "consultar"),
        ("El cargo de mi tarjeta no aparece en el resumen", "consultar"),
        ("El pago con la tarjeta no aparece", "consultar"),
        ("A compra no meu cartão, não acho no extrato", "consultar"),
        # Os mesmos, com o tipo do cartão.
        ("La compra con mi tarjeta de crédito no aparece", "consultar"),
        ("Não acho a compra no cartão de crédito", "consultar"),
        ("Esqueci a senha do cartão de débito", "fora_de_escopo"),
        ("Se me cayó la app cuando pagaba con la tarjeta", "desconhecida"),
    ],
)
def test_verbo_de_perda_sem_o_cartao_perto_nao_e_fraude(texto, intencao):
    assert ler(texto).intencao == intencao


@pytest.mark.parametrize(
    "texto",
    [
        # O cartão seguro, a tela do app, o cartão cancelado, a fatura ou o extrato do cartão não
        # são perda (auditoria do dev, 02/10): bloqueariam o cartão.
        "Olvidé mi tarjeta en casa, ¿puedo pagar con el celular?",
        "Esqueci meu cartão em casa, posso pagar pelo celular?",
        "La tarjeta nueva no aparece en la app",
        "Mi celular desapareció de la lista de dispositivos",
        "Esqueci a fatura do cartão em casa",
        "Não acho o extrato do cartão no app",
        "Esqueci a fatura do cartão",
        "No encuentro el resumen de la tarjeta",
    ],
)
def test_cartao_seguro_ou_outro_objeto_do_cartao_nao_e_perda(texto):
    assert ler(texto).intencao != "fraude"


@pytest.mark.parametrize(
    "texto",
    [
        # Mais longe que 3 palavras já é outra oração: continua perda.
        "Perdi meu cartão e não aparece no aplicativo a opção de bloquear",
        "Se me perdió la tarjeta en el sistema de transporte",
        "Perdí la tarjeta y no aparece en la app",
    ],
)
def test_perda_seguida_de_outra_oracao_continua_perda(texto):
    assert ler(texto).intencao == "fraude"


@pytest.mark.parametrize(
    "texto",
    [
        # Outra pessoa usou, roubou, sacou ou pediu dinheiro: relato de fraude, que até o #57 ia ao
        # atendente pelos termos soltos de humano (REG-12 no d9dfad0).
        "alguien utilizó mi tarjeta sin mi permiso",
        "alguien está usando mi número",
        "alguien me robó con un número falso",
        "Alguien hizo compras con mi tarjeta",
        "una persona sacó dinero de mi cuenta",
        "un desconocido entró a mi cuenta",
        "alguém está usando meu cartão",
        "alguém roubou meu dinheiro da conta",
        "uma pessoa fez compras no meu cartão",
        "alguém se passou por mim e fez um pix",
        "um estranho acessou minha conta",
        "Mi tarjeta se robó anoche",
        # Golpe contado como história; a senha não faz virar fora de escopo (ACH-171, REG-12).
        "Alguém me ligou falando que era do banco e conseguiu minha senha",
        "Recebi uma ligação de alguém que se passava por um atendente do banco",
        "Un señor haciéndose pasar por el banco me pidió la clave",
        "Me llamó alguien que se hacía pasar por el banco y consiguió mi clave",
        "Um homem conseguiu minha senha pelo telefone",
        "Meu cartão se roubou ontem",
        # O leitor lia com confiança como contestação (ACH-182, LLM-01): agora as regras leem antes.
        "Alguien anda gastando con mi plástico en tiendas donde nunca he puesto un pie",
        "Tem alguém gastando com o meu plástico em loja que eu nunca fui",
        "alguien está gastando con mi tarjeta",
        "perdí mi plástico ayer",
    ],
)
def test_relato_de_que_outra_pessoa_usou_ou_roubou_e_fraude(texto):
    assert ler(texto).intencao == "fraude"


@pytest.mark.parametrize(
    ("texto", "intencao"),
    [
        # Leituras que o leitor fazia com confiança e erradas (ACH-182, LLM-01): o cartão na gíria
        # e o pedido de pessoa no plural agora são das regras.
        ("Necesito que congelen mi plástico un ratito", "bloquear"),
        ("Quero travar meu plástico um pouquinho", "bloquear"),
        ("Bloqueen mi plástico, por favor", "bloquear"),
        ("Pásenme con un ser humano, este chat no me sirve", "humano"),
        ("Me passem para um atendente", "humano"),
        # O termo com uma letra a mais no fim é outra palavra, não erro de digitação (ACH-172).
        ("Preciso do meu cartão pessoal", "desconhecida"),
        ("Necesito mi tarjeta personal", "desconhecida"),
    ],
)
def test_girias_e_plurais_que_o_leitor_lia_errado_sao_das_regras(texto, intencao):
    assert ler(texto).intencao == intencao


@pytest.mark.parametrize(
    ("texto", "pergunta"),
    [
        # As flexões de "evitar" e "cuidar" também são pergunta de prevenção (REG-16); com vítima,
        # continua sendo relato.
        ("¿Cómo evito caer en una estafa?", True),
        ("Como evito cair em golpe?", True),
        ("¿Cómo me cuido de una estafa por WhatsApp?", True),
        ("Me robaron la tarjeta, ¿cómo evito que la usen?", False),
    ],
)
def test_flexoes_de_evitar_e_cuidar_sao_prevencao(texto, pergunta):
    assert ler(texto).intencao == "fraude"
    assert interpretacao.prevencao(texto) is pergunta


@pytest.mark.parametrize(
    ("texto", "pergunta"),
    [
        # A hipótese de perda é pergunta: lida como fraude (pelo leitor), vai ao atendente sem
        # bloquear (REG-20). Com vítima, continua relato.
        ("En caso de perder la tarjeta, ¿cómo la bloqueo?", True),
        ("Caso eu perca o cartão, o que faço?", True),
        ("¿Qué pasa si pierdo la tarjeta?", True),
        ("O que acontece se eu perder o cartão?", True),
        ("Perdí la tarjeta, en caso de que la usen ¿qué hago?", False),
    ],
)
def test_hipotese_de_perda_e_prevencao(texto, pergunta):
    assert interpretacao.prevencao(texto) is pergunta


@pytest.mark.parametrize(
    ("texto", "pergunta"),
    [
        # A pergunta condicional sobre o uso por outra pessoa vai ao atendente sem bloquear (P3);
        # o relato seguido de pergunta, ou a pergunta com vítima, continua bloqueando.
        ("¿Qué hago si alguien usó mi tarjeta?", True),
        ("O que fazer se alguém usou meu cartão?", True),
        ("¿Cómo sé si alguien está usando mi tarjeta?", True),
        ("alguien usó mi tarjeta, ¿qué hago?", False),
        ("¿Qué hago si me robaron la tarjeta?", False),
    ],
)
def test_pergunta_condicional_sobre_uso_por_outra_pessoa_e_prevencao(texto, pergunta):
    assert ler(texto).intencao == "fraude"
    assert interpretacao.prevencao(texto) is pergunta


@pytest.mark.parametrize(
    "texto",
    [
        # A mesma pessoa sem verbo de uso, roubo ou saque, ou o verbo no presente (pergunta).
        "Una persona me cobró de más en la tienda.",
        "¿Qué pasa si alguien usa mi tarjeta?",
        "Quero que uma pessoa veja meu caso",
        "alguien del banco me llamó ayer",
        "Esqueci minha senha do aplicativo",
        "¿Cómo cambio mi clave?",
    ],
)
def test_outra_pessoa_sem_uso_nem_roubo_nao_e_relato_de_fraude(texto):
    assert ler(texto).intencao != "fraude"


@pytest.mark.parametrize(
    "texto",
    [
        # O papel antes do verbo é quem atendeu de verdade, não golpe (ACH-173, REG-18).
        "Liguei e o atendente falou que era só esperar 24 horas",
        "El asesor dijo que era un error del sistema y que me devolverían el dinero",
        "O operador falou que era normal demorar o estorno",
        "Meu filho falou que era para eu perguntar aqui qual é o limite do cartão",
        "O gerente disse que era um erro e que iam corrigir",
    ],
)
def test_o_que_o_atendente_de_verdade_disse_nao_e_golpe(texto):
    assert ler(texto).intencao != "fraude"


@pytest.mark.parametrize(
    "texto",
    [
        # Com o verbo antes do papel, continua golpe.
        "Um falso atendente falou que era do banco",
        "Me llamó un hombre que dijo que era del banco",
        "Recebi uma ligação de alguém que se passava por um atendente do banco",
    ],
)
def test_verbo_e_depois_o_papel_continua_golpe(texto):
    assert ler(texto).intencao == "fraude"


@pytest.mark.parametrize(
    "texto",
    [
        # Quem se apresentou como outro (o resto do ACH-171, REG-12 no 4c62c69): o funcionário do
        # banco, o parente que pede dinheiro, o agente disfarçado...
        "Acabo de enviar 2000 pesos por pix a alguien que me aseguró ser mi primo",
        "Uma pessoa se fazendo passar por atendente do banco me ligou",
        "Me fizeram uma ligação disfarçada de agente bancário e eu acreditei",
        # ... quem acreditou que era outro...
        "Le envié dinero a alguien creyendo que era mi sobrino",
        "Enviei dinheiro para alguém achando que era meu sobrinho",
        "Mandei dinheiro para alguém alegando que era meu parente",
        # ... o agente suposto e o código facilitado.
        "Un supuesto agente del banco me llamó ayer",
        "Me llamaron y les facilité el código y la clave",
    ],
)
def test_golpe_de_quem_se_apresentou_como_outro(texto):
    assert ler(texto).intencao == "fraude"


@pytest.mark.parametrize(
    ("texto", "golpe"),
    [
        # Apresentar-se como outro é golpe com o parente ou com o pedido depois (ACH-179)...
        ("Mandé dinero a una persona que se presentó como mi sobrino", True),
        ("Una persona que se presentó como empleado del banco me pidió la clave", True),
        ("Me llamó alguien que decía trabajar en este banco y me pidió la clave", True),
        ("Um homem se apresentou como funcionário do banco e me pediu a senha", True),
        # ... e não é quando o atendente de verdade se apresenta e pede outra coisa.
        ("La señora se presentó como gerente y me pidió que esperara un momento", False),
        ("Se presentó como asesor y me explicó cómo cambiar la clave", False),
    ],
)
def test_apresentar_se_como_outro_e_golpe_com_o_parente_ou_o_pedido(texto, golpe):
    assert (ler(texto).intencao == "fraude") is golpe


@pytest.mark.parametrize(
    "texto",
    [
        # O uso por outra pessoa contado de outros jeitos (o resto do ACH-171, REG-12 no 4c62c69).
        "Tengo un problema con mi tarjeta, alguien la utilizó sin autorización",
        "Creo que alguien la está usando sin mi permiso",
        "Hay transacciones que no hice, alguien debió haber usado mi tarjeta",
        "Mi tarjeta fue utilizada por una persona sin autorización",
        "Alguien ha accedido a mi cuenta y hace transferencias",
        "Alguien está entrando en mi cuenta",
        "Alguien ha estado haciendo pagos con mi tarjeta",
        "Alguien abrió una cuenta a mi nombre",
        "Creo que alguien obtuvo los datos de mi tarjeta y la usó",
        "Acho que alguém conseguiu obter os dados do meu cartão",
        "Alguém está usando a minha conta",
        "Acho que alguém pegou meu cartão",
        "Alguien intentó realizar una compra con mi tarjeta en Miami",
        "Una persona usó fraudulentamente mi tarjeta",
    ],
)
def test_uso_por_outra_pessoa_contado_de_outros_jeitos_e_fraude(texto):
    assert ler(texto).intencao == "fraude"


@pytest.mark.parametrize(
    "texto",
    [
        # Senha ou código pedidos sem ser os do cliente, ou negados, não são golpe (REG-17).
        "La app me pidió un código de verificación",
        "O caixa pediu a senha duas vezes",
        "Minha mãe não conseguiu trocar a senha",
        "Ele não conseguiu minha senha, eu desliguei antes",
    ],
)
def test_senha_pedida_sem_ser_a_do_cliente_ou_negada_nao_e_golpe(texto):
    assert ler(texto).intencao != "fraude"


@pytest.mark.parametrize(
    "texto",
    [
        # Mensagens comuns com os termos de golpe da leva de 02/10, que bloqueariam o cartão:
        # a senha pedida pelo caixa, pelo app ou pelo caixa eletrônico...
        "El cajero automático me pidió mi pin dos veces y no me dio el dinero",
        "O app pediu minha senha para entrar",
        "La página me pidió mi clave y no la acepta",
        "O sistema conseguiu recuperar minha senha",
        # ... o dinheiro recebido de outra pessoa...
        "Alguém transferiu dinheiro para mim por engano",
        "Una persona me transfirió el pago del alquiler",
        # ... outra pessoa usando outra coisa, e o plástico que não é o cartão.
        "Uma pessoa está usando o caixa ao meu lado",
        "Una persona está entrando a la tienda",
        "Una persona intentó realizar el pago por mí en la caja",
        "Mi hermana la usó con mi permiso",
        # Os termos do #77 em mensagens comuns (ACH-179, REG-24): "de ustedes", o cadastro, o
        # atendente de verdade que se apresenta e o "fraudulenta" negado.
        "Recibí un cargo y pensé que era de ustedes, pero no reconozco el comercio",
        "Vi um débito e achei que era de vocês, mas não reconheço a loja",
        "Pensando que era de vocês a cobrança, não reclamei antes",
        "Ya les facilité mis datos, ¿cuándo me llega la tarjeta?",
        "La señora que me atendió en la sucursal se presentó como gerente y me ayudó mucho",
        "El chico que me atendió dijo trabajar en el banco hace diez años",
        "O rapaz que me atendeu disse trabalhar no banco há dez anos",
        "No creo que el cobro haya sido de manera fraudulenta, solo quiero entenderlo",
        "La bolsa de plástico que perdí no importa, quiero ver mi saldo",
        # A senha pedida sem dizer por quem não separa golpe de rotina: fica fora de escopo, e a
        # conversa oferece o atendente.
        "Me pidieron mi clave por WhatsApp",
    ],
)
def test_mensagens_comuns_com_os_termos_de_golpe_nao_sao_fraude(texto):
    assert ler(texto).intencao != "fraude"


@pytest.mark.parametrize(
    "texto",
    [
        # DEV-080 (ACH-159, HUM-01): a pessoa citada sem pedido não é pedido de atendente.
        "Una persona me cobró de más en la tienda.",
        "Uma pessoa me cobrou a mais na loja.",
        "O atendente da loja foi muito educado.",
        "El agente de viajes me vendió el paquete",
    ],
)
def test_pessoa_citada_sem_pedido_nao_e_pedido_de_atendente(texto):
    assert ler(texto).intencao != "humano"


@pytest.mark.parametrize(
    ("texto", "intencao"),
    [
        # Com o verbo de pedido perto, é; e "gerente" vale com os pedidos de PT.
        ("Chama um gerente.", "humano"),
        ("Me coloca com um gerente.", "humano"),
        ("quiero que una persona revise mi caso", "humano"),
        # A mensagem que é só a pessoa continua sendo pedido.
        ("Agente", "humano"),
        ("Un humano por favor", "humano"),
        ("atendente agora", "humano"),
        # O "por favor" abreviado (REG-01: "asesor pfv" ia ao leitor, que o lia fora de escopo).
        ("asesor pfv", "humano"),
        ("um atendente pls", "humano"),
        ("porfa un asesor", "humano"),
    ],
)
def test_pessoa_com_verbo_de_pedido_ou_sozinha_e_pedido_de_atendente(texto, intencao):
    assert ler(texto).intencao == intencao


@pytest.mark.parametrize(
    ("texto", "intencao"),
    [
        # Cobrança a mais é contestação ("uma pessoa me cobrou a mais" não gerava o pré-caso).
        ("Una persona me cobró de más en la tienda.", "contestar"),
        ("Uma pessoa me cobrou a mais na loja.", "contestar"),
        ("Me cobraron 20 dólares de más", "contestar"),
        ("O mercado me cobrou a mais", "contestar"),
        ("Cobraram mais caro do que o anunciado", "contestar"),
        ("Me cobraron más caro que el precio de la vitrina", "contestar"),
        # Sem o verbo de cobrar, "mais" e "más" continuam consulta.
        ("Qual é a cobrança mais recente?", "consultar"),
        ("¿Cuál es el cobro más reciente?", "consultar"),
    ],
)
def test_cobranca_a_mais_e_contestacao(texto, intencao):
    assert ler(texto).intencao == intencao


@pytest.mark.parametrize(
    "texto",
    [
        # A cobrança a mais negada não é contestação (sondagem da validação no 0d811eb).
        "No me cobraron de más, solo quería saber el saldo",
        "Não me cobraram a mais, só quero saber o saldo",
        "Nunca me cobraron de más aquí",
    ],
)
def test_cobranca_a_mais_negada_nao_e_contestacao(texto):
    assert ler(texto).intencao != "contestar"


@pytest.mark.parametrize(
    "texto",
    [
        # ACH-181: os pedidos de pessoa com outros verbos (regressão do PEDIDO_DE_PESSOA).
        "Me pasas con una persona",
        "Conéctame con un agente",
        "Dame un asesor",
        "Llámame un humano",
        "Me conecta com uma pessoa",
        "Me liga um atendente",
        "Me põe em contato com um humano",
    ],
)
def test_outros_verbos_de_pedido_de_pessoa(texto):
    assert ler(texto).intencao == "humano"


def test_plural_de_termo_nao_e_corrigido_para_o_termo():
    """Regressão do DEV-060 no ACH-144 (REG-14): "golpes" não vira "golpe", nem "estafas" vira
    "estafa"; o erro de uma letra continua corrigido."""
    texto = "Estoy preocupado con tantas estafas y golpes"
    assert interpretacao.corrigir(texto) == (texto, ())
    assert ler("No reconosco un cargo").intencao == "contestar"
