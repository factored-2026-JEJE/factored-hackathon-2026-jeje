"""Respostas ES/PT a partir de cláusulas aprovadas (DEV-013).

Cada decisão da política vira uma cláusula com texto aprovado nas duas línguas; os únicos valores
variáveis vêm de fatos verificados (transação da curada, protocolo relido do banco). Nenhuma
cláusula promete estorno, prazo ou resultado (verificado em teste). O significado dos códigos de
recusa é o genérico da ISO 8583, rotulado como tal: não é a política do banco emissor.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from string import Formatter
from typing import Literal, get_args

Idioma = Literal["es", "pt"]
IDIOMAS: tuple[Idioma, ...] = get_args(Idioma)
# Status de transação que o atendimento sabe dizer (rótulos em ESTADO).
Status = Literal["Approved", "Declined", "Pending", "Reversed"]

# Significado genérico dos códigos catalogados (ISO 8583; simulado, rotulado na resposta).
MOTIVO_DO_CODIGO: dict[str, dict[Idioma, str]] = {
    "51": {"es": "fondos insuficientes", "pt": "saldo insuficiente"},
    "14": {"es": "número de tarjeta inválido", "pt": "número de cartão inválido"},
    "54": {"es": "tarjeta vencida", "pt": "cartão vencido"},
    "05": {"es": "no autorizada por el emisor", "pt": "não autorizada pelo emissor"},
}

# O pedido em andamento, dito de volta ao cliente no resumo (RESUMO-TRANSACAO).
PEDIDO: dict[str, dict[Idioma, str]] = {
    "consultar": {"es": "consultar una transacción", "pt": "consultar uma transação"},
    "contestar": {"es": "pedir la revisión de un cobro", "pt": "pedir a revisão de uma cobrança"},
}

ESTADO: dict[Status, dict[Idioma, str]] = {
    "Approved": {"es": "aprobada", "pt": "aprovada"},
    "Declined": {"es": "rechazada", "pt": "recusada"},
    "Pending": {"es": "pendiente", "pt": "pendente"},
    "Reversed": {"es": "revertida", "pt": "estornada"},
}

# Estado do pré-caso (app.pre_casos.estado); a automação só grava "recebido".
ESTADO_DO_CASO: dict[str, dict[Idioma, str]] = {
    "recebido": {"es": "recibida, en espera de revisión", "pt": "recebido, aguardando revisão"},
}

CLAUSULAS: dict[str, dict[Idioma, str]] = {
    "POL-CON-01": {
        "es": "La transacción {transacao} fue aprobada.",
        "pt": "A transação {transacao} foi aprovada.",
    },
    "POL-CON-03": {
        "es": "La transacción {transacao} fue rechazada. Motivo informado en el código {codigo}: "
        "{motivo} (significado genérico del estándar ISO 8583).",
        "pt": "A transação {transacao} foi recusada. Motivo informado no código {codigo}: "
        "{motivo} (significado genérico do padrão ISO 8583).",
    },
    "POL-CON-04": {
        "es": "La transacción {transacao} fue rechazada y no tenemos el motivo registrado. "
        "Si quieres, te comunico con un agente.",
        "pt": "A transação {transacao} foi recusada e não temos o motivo registrado. "
        "Se quiser, eu passo você para um atendente.",
    },
    "POL-CON-05": {
        "es": "La transacción {transacao} está {estado}. Te informo lo que consta hoy en el "
        "registro.",
        "pt": "A transação {transacao} está {estado}. Informo o que consta hoje no registro.",
    },
    "POL-CON-02": {
        "es": "Encontré más de una transacción posible. ¿Cuál de estas es?\n{opcoes}",
        "pt": "Encontrei mais de uma transação possível. Qual destas é?\n{opcoes}",
    },
    # Muitas transações possíveis (DEV-037): pergunta pelo campo que mais divide, no lugar da lista.
    "CON-PERGUNTA-data": {
        "es": "Encontré varias transacciones posibles. ¿Recuerdas la fecha?",
        "pt": "Encontrei várias transações possíveis. Você lembra a data?",
    },
    "CON-PERGUNTA-valor": {
        "es": "Encontré varias transacciones posibles. ¿Recuerdas el valor?",
        "pt": "Encontrei várias transações possíveis. Você lembra o valor?",
    },
    "CON-PERGUNTA-comercio": {
        "es": "Encontré varias transacciones posibles. ¿En qué comercio fue?",
        "pt": "Encontrei várias transações possíveis. Em qual estabelecimento foi?",
    },
    # Uma só possível, sem pista que garanta (o número solto, ACH-143): a transação vira opção.
    "CON-UMA-POSSIVEL": {
        "es": "Encontré una transacción que puede ser. ¿Es esta?\n{opcoes}",
        "pt": "Encontrei uma transação que pode ser. É esta?\n{opcoes}",
    },
    # A transação proposta não é a certa (ACH-145): o pedido continua.
    "CON-OUTRA": {
        "es": "Entendido, no es esa. ¿Cuál es? ¿Me indicas el valor, la fecha o el comercio?",
        "pt": "Entendi, não é essa. Qual é? Pode me dizer o valor, a data ou o estabelecimento?",
    },
    "CON-NENHUMA": {
        "es": "No encontré esa transacción en tu cuenta. ¿Me indicas el valor, la fecha o el "
        "comercio?",
        "pt": "Não encontrei essa transação na sua conta. Pode me dizer o valor, a data ou o "
        "estabelecimento?",
    },
    "POL-DISP-01": {
        "es": "Puedo registrar una solicitud de revisión (pre-caso) de la transacción {transacao}. "
        "Esto no devuelve el dinero ni resuelve la disputa. ¿Confirmas?",
        "pt": "Posso registrar um pedido de revisão (pré-caso) da transação {transacao}. "
        "Isso não devolve o dinheiro nem resolve a contestação. Você confirma?",
    },
    "PRE-CASO-REGISTRADO": {
        "es": "Registré la solicitud con el protocolo {protocolo}. Es un registro para revisión, "
        "no un reembolso.",
        "pt": "Registrei o pedido com o protocolo {protocolo}. É um registro para revisão, "
        "não um reembolso.",
    },
    "POL-DISP-03": {
        "es": "Ya existe la solicitud {protocolo} para la transacción {transacao}.",
        "pt": "Já existe o pedido {protocolo} para a transação {transacao}.",
    },
    "POL-CASO-01": {
        "es": "Tu solicitud de revisión {protocolo}, de la transacción {transacao}, se registró el "
        "{registro} y está {estado_caso}. No tengo más información sobre la revisión ni un plazo.",
        "pt": "Seu pedido de revisão {protocolo}, da transação {transacao}, foi registrado em "
        "{registro} e está {estado_caso}. Não tenho mais informações sobre a revisão nem um prazo.",
    },
    "POL-CASO-02": {
        "es": "Estas son tus solicitudes de revisión:\n{casos}\nNo tengo más información sobre la "
        "revisión ni un plazo.",
        "pt": "Estes são os seus pedidos de revisão:\n{casos}\nNão tenho mais informações sobre a "
        "revisão nem um prazo.",
    },
    "CASO-ITEM": {
        "es": "{protocolo}: transacción {transacao}, registrada el {registro}, {estado_caso}",
        "pt": "{protocolo}: transação {transacao}, registrado em {registro}, {estado_caso}",
    },
    "POL-CASO-03": {
        "es": "No encontré solicitudes de revisión registradas en tu cuenta. Puedo consultar una "
        "transacción o registrar una solicitud de revisión de un cobro que no reconoces.",
        "pt": "Não encontrei pedidos de revisão registrados na sua conta. Posso consultar uma "
        "transação ou registrar um pedido de revisão de uma cobrança que você não reconhece.",
    },
    "POL-DISP-02": {
        "es": "La transacción {transacao} está {estado} y no se puede disputar automáticamente. "
        "Te comunico con un agente.",
        "pt": "A transação {transacao} está {estado} e não pode ser contestada automaticamente. "
        "Vou passar você para um atendente.",
    },
    "POL-HUM-01": {
        "es": "Por seguridad, un agente va a atender este caso. Ya le paso el resumen.",
        "pt": "Por segurança, um atendente vai cuidar deste caso. Já passo o resumo para ele.",
    },
    "POL-HUM-02": {
        "es": "Esta solicitud necesita la revisión de un agente. Ya le paso el resumen.",
        "pt": "Este pedido precisa da revisão de um atendente. Já passo o resumo para ele.",
    },
    "POL-HUM-04": {
        "es": "Por seguridad, las solicitudes sobre transacciones hechas de noche por la app o la "
        "web por encima del límite automático las revisa un agente. Ya le paso el resumen.",
        "pt": "Por segurança, pedidos sobre transações feitas à noite pelo app ou pela web acima "
        "do limite automático são revisados por um atendente. Já passo o resumo para ele.",
    },
    "POL-HUM-05": {
        "es": "Esta compra es más antigua que el plazo que puedo atender por aquí, así que la "
        "revisa un agente. Ya le paso el resumen.",
        "pt": "Esta compra é mais antiga que o prazo que eu consigo atender por aqui, então um "
        "atendente vai revisar. Já passo o resumo para ele.",
    },
    "POL-HUM-06": {
        "es": "Ya hay varias solicitudes de revisión recientes en tu cuenta, así que esta la "
        "revisa un agente. Ya le paso el resumen.",
        "pt": "Já há vários pedidos de revisão recentes na sua conta, então este é revisado por um "
        "atendente. Já passo o resumo para ele.",
    },
    "POL-SEG-01": {
        "es": "Las transferencias de alto valor pasan por un análisis de seguridad. Un agente de "
        "seguridad va a revisar tu caso; ya le paso el resumen.",
        "pt": "Transferências de alto valor passam por uma análise de segurança. Um atendente da "
        "segurança vai revisar o seu caso; já passo o resumo para ele.",
    },
    "POL-HUM-03": {
        "es": "Te comunico con un agente. Ya le paso el resumen de la conversación.",
        "pt": "Vou passar você para um atendente. Já envio o resumo da conversa.",
    },
    "POL-ESC-01": {
        "es": "Solo puedo ayudar con consultas y solicitudes de revisión de tus transacciones.",
        "pt": "Só consigo ajudar com consultas e pedidos de revisão das suas transações.",
    },
    "POL-ID-02": {
        "es": "Por seguridad no busco transacciones por identificadores escritos en el chat. "
        "¿Me indicas el valor, la fecha o el comercio?",
        "pt": "Por segurança, não busco transações por identificadores escritos no chat. "
        "Pode me dizer o valor, a data ou o estabelecimento?",
    },
    # Bloqueio simulado de cartão (PRD-007).
    "POL-BLQ-01": {
        "es": "Como el acceso es desde un dispositivo nuevo, un agente va a confirmar o deshacer "
        "el bloqueo. Ya le paso el resumen.",
        "pt": "Como o acesso é de um dispositivo novo, um atendente vai confirmar ou desfazer o "
        "bloqueio. Já passo o resumo para ele.",
    },
    "POL-BLQ-02": {
        "es": "Si fue un error, pídeme deshacerlo.",
        "pt": "Se foi engano, peça para desfazer.",
    },
    "POL-BLQ-03": {
        "es": "No encontré ninguna tarjeta activa para bloquear en tu cuenta.",
        "pt": "Não encontrei nenhum cartão ativo para bloquear na sua conta.",
    },
    "CARTAO-ENCERRADO": {
        "es": "La {cartao} está cerrada en el banco: no hace falta bloquearla.",
        "pt": "O {cartao} está encerrado no banco: não precisa bloquear.",
    },
    "POL-BLQ-04": {
        "es": "¿Confirmas que quieres deshacer el bloqueo de tu {cartao} (referencia {bloqueio})? "
        "Responde sí o no.",
        "pt": "Você confirma que quer desfazer o bloqueio do seu {cartao} (referência {bloqueio})? "
        "Responda sim ou não.",
    },
    "POL-BLQ-05": {
        "es": "Para deshacer un bloqueo, un agente revisa la solicitud. Ya le paso el resumen.",
        "pt": "Para desfazer um bloqueio, um atendente revisa o pedido. Já passo o resumo para "
        "ele.",
    },
    "POL-BLQ-06": {
        "es": "¿Cuál tarjeta quieres bloquear?\n{opcoes}\nResponde con el número de la opción o "
        "con los 4 últimos dígitos.",
        "pt": "Qual cartão você quer bloquear?\n{opcoes}\nResponda com o número da opção ou com "
        "os 4 últimos dígitos.",
    },
    "POL-BLQ-07": {
        "es": "Puedo bloquear tu tarjeta ahora mismo por aquí. ¿Quieres que la bloquee ahora? "
        "Responde sí o no.",
        "pt": "Posso bloquear o seu cartão agora mesmo por aqui. Quer que eu bloqueie agora? "
        "Responda sim ou não.",
    },
    "POL-BLQ-06-DESBLOQUEIO": {
        "es": "¿Cuál tarjeta quieres desbloquear?\n{opcoes}\nResponde con el número de la opción "
        "o con los 4 últimos dígitos.",
        "pt": "Qual cartão você quer desbloquear?\n{opcoes}\nResponda com o número da opção ou "
        "com os 4 últimos dígitos.",
    },
    "POL-BLQ-06-FRAUDE": {
        "es": "Mientras tanto, puedo bloquear ahora la tarjeta afectada. ¿Cuál es?\n{opcoes}\n"
        "Responde con el número de la opción o con los 4 últimos dígitos.",
        "pt": "Enquanto isso, posso bloquear agora o cartão afetado. Qual é?\n{opcoes}\n"
        "Responda com o número da opção ou com os 4 últimos dígitos.",
    },
    # Mensagens de fluxo da conversa (G10): não decidem nada, só conduzem o próximo passo.
    "SAUDACAO": {
        "es": "Hola. Puedo consultar el estado de tus transacciones y registrar una solicitud de "
        "revisión de un cobro que no reconoces. ¿En qué te ayudo?",
        "pt": "Olá. Posso consultar a situação das suas transações e registrar um pedido de "
        "revisão de uma cobrança que você não reconhece. Como posso ajudar?",
    },
    "AJUDA": {
        "es": "No entendí tu pedido. Puedo consultar una transacción o registrar una solicitud de "
        "revisión. ¿Me indicas el valor, la fecha o el comercio?",
        "pt": "Não entendi o seu pedido. Posso consultar uma transação ou registrar um pedido de "
        "revisão. Pode me dizer o valor, a data ou o estabelecimento?",
    },
    "AGRADECIMENTO": {
        "es": "¡Con gusto! ¿Te ayudo con algo más?",
        "pt": "Por nada! Posso ajudar com mais alguma coisa?",
    },
    "CONFIRMACAO-PENDENTE": {
        "es": "¿Confirmas el registro de la solicitud de revisión de la transacción {transacao}? "
        "Responde sí o no.",
        "pt": "Você confirma o registro do pedido de revisão da transação {transacao}? "
        "Responda sim ou não.",
    },
    "PROPOSTA-VENCIDA": {
        "es": "La confirmación anterior ya no es válida; revisé de nuevo la transacción.",
        "pt": "A confirmação anterior não vale mais; conferi a transação de novo.",
    },
    "CANCELADO": {
        "es": "Listo, no registré nada. ¿Te ayudo con algo más?",
        "pt": "Tudo bem, não registrei nada. Posso ajudar com mais alguma coisa?",
    },
    # Mensagem que não cabe na etapa: o que foi entendido e o que se está tentando, com a oferta
    # do atendente; o "não" volta à etapa.
    "RESUMO-PEDIDO": {
        "es": "No logré entender tu pedido. ¿Quieres que te comunique con un agente?",
        "pt": "Não consegui entender o seu pedido. Quer que eu passe você para um atendente?",
    },
    "RESUMO-TRANSACAO": {
        "es": "Entendí que quieres {pedido} y estoy buscando la transacción, pero todavía no la "
        "identifiqué.",
        "pt": "Entendi que você quer {pedido} e estou procurando a transação, mas ainda não "
        "consegui identificá-la.",
    },
    "RESUMO-CONFIRMACAO": {
        "es": "Estoy esperando tu confirmación para registrar la solicitud de revisión de la "
        "transacción {transacao}.",
        "pt": "Estou esperando sua confirmação para registrar o pedido de revisão da transação "
        "{transacao}.",
    },
    "RESUMO-FOCO": {
        "es": "Sobre la transacción {transacao}: en el registro consta que está {estado}, y no "
        "tengo más información que esa.",
        "pt": "Sobre a transação {transacao}: no registro consta que ela está {estado}, e não "
        "tenho outra informação além disso.",
    },
    "OFERTA-ATENDENTE": {
        "es": "Si no es eso, ¿quieres que te comunique con un agente?",
        "pt": "Se não for isso, quer que eu passe você para um atendente?",
    },
    # A mensagem que tenta mudar as regras (ACH-203): o que o atendimento faz, sem oferecer nada.
    "INSTRUCAO": {
        "es": "Por aquí puedo consultar transacciones, registrar una solicitud de revisión, "
        "bloquear tu tarjeta o pasarte con un agente. ¿Qué necesitas?",
        "pt": "Por aqui eu posso consultar transações, registrar um pedido de revisão, "
        "bloquear seu cartão ou passar você para um atendente. Do que você precisa?",
    },
    "OFERTA-FORA": {
        "es": "Para eso, ¿quieres que te comunique con un agente?",
        "pt": "Para isso, quer que eu passe você para um atendente?",
    },
    "RETOMAR": {
        "es": "Está bien, sigamos.",
        "pt": "Tudo bem, vamos continuar.",
    },
    "RETOMAR-LIVRE": {
        "es": "Está bien. ¿En qué más te ayudo?",
        "pt": "Tudo bem. Em que mais posso ajudar?",
    },
    "ATENDIMENTO": {
        "es": "Referencia de la atención: {atendimento}.",
        "pt": "Referência do atendimento: {atendimento}.",
    },
    "ENCERRADA": {
        "es": "Esta conversación se cerró porque los datos se actualizaron. Abre una nueva "
        "conversación para seguir.",
        "pt": "Esta conversa foi encerrada porque os dados foram atualizados. Abra uma nova "
        "conversa para continuar.",
    },
    # O bloqueio feito ou encontrado, relido do banco e rotulado como simulação (PRD-007).
    "BLOQUEIO-FEITO": {
        "es": "Bloqueé tu {cartao} ({como}, referencia {bloqueio}).",
        "pt": "Bloqueei o seu {cartao} ({como}, referência {bloqueio}).",
    },
    "BLOQUEIO-EXISTENTE": {
        "es": "Tu {cartao} ya está bloqueada (referencia {bloqueio}).",
        "pt": "O seu {cartao} já está bloqueado (referência {bloqueio}).",
    },
    "CARTAO-INATIVO": {
        "es": "Tu {cartao} no está activa, así que no la bloqueé.",
        "pt": "O seu {cartao} não está ativo, então não o bloqueei.",
    },
    "BLOQUEIOS-ATIVOS": {
        "es": "Tarjetas ya bloqueadas por aquí: {bloqueados}.",
        "pt": "Cartões já bloqueados por aqui: {bloqueados}.",
    },
    "BLOQUEIO-NAO-IDENTIFICADO": {
        "es": "No identifiqué cuál tarjeta, así que no bloqueé ninguna.",
        "pt": "Não identifiquei qual cartão, então não bloqueei nenhum.",
    },
    "BLOQUEIO-CANCELADO": {
        "es": "Listo, no bloqueé ninguna tarjeta. ¿Te ayudo con algo más?",
        "pt": "Tudo bem, não bloqueei nenhum cartão. Posso ajudar com mais alguma coisa?",
    },
    "DESBLOQUEIO-FEITO": {
        "es": "Listo: deshice el bloqueo de tu {cartao} (referencia {bloqueio}).",
        "pt": "Pronto: desfiz o bloqueio do seu {cartao} (referência {bloqueio}).",
    },
    "DESBLOQUEIO-CANCELADO": {
        "es": "Listo, el bloqueo sigue. ¿Te ayudo con algo más?",
        "pt": "Tudo bem, o bloqueio continua. Posso ajudar com mais alguma coisa?",
    },
    "RESUMO-CARTAO": {
        "es": "Entendí que quieres bloquear una tarjeta, pero no identifiqué cuál. ¿Quieres que "
        "te comunique con un agente?",
        "pt": "Entendi que você quer bloquear um cartão, mas não identifiquei qual. Quer que eu "
        "passe você para um atendente?",
    },
    "COM-HUMANO": {
        "es": "Tu caso ya está con un agente (referencia {atendimento}); la conversación sigue con "
        "esa persona.",
        "pt": "Seu caso já está com um atendente (referência {atendimento}); a conversa segue com "
        "essa pessoa.",
    },
}


@dataclass(frozen=True)
class TransacaoVerificada:
    """Campos exibíveis de uma transação lida da curada para o cliente da sessão."""

    transaction_id: str
    transaction_date: datetime
    amount: Decimal
    currency: str
    merchant_name: str | None
    transaction_status: str
    transaction_type: str | None = None


def valor(quantia: Decimal, moeda: str) -> str:
    """Sempre duas casas, milhar com ponto e decimal com vírgula (igual nas duas línguas)."""
    inteiro, _, centavos = f"{quantia:,.2f}".partition(".")
    return f"{moeda} {inteiro.replace(',', '.')},{centavos}"


PREPOSICAO: dict[Idioma, str] = {"es": "en", "pt": "em"}


# Sem comércio (saque, pagamento, transferência), o tipo diz o que foi: o identificador interno
# nunca vai para o cliente (ACH-167).
TIPO_DE_TRANSACAO: dict[str, dict[Idioma, str]] = {
    "Purchase": {"es": "de compra", "pt": "de compra"},
    "Withdrawal": {"es": "de retiro", "pt": "de saque"},
    "Transfer": {"es": "de transferencia", "pt": "de transferência"},
    "Payment": {"es": "de pago", "pt": "de pagamento"},
    "Deposit": {"es": "de depósito", "pt": "de depósito"},
    "Adjustment": {"es": "de ajuste", "pt": "de ajuste"},
}


def descrever(t: TransacaoVerificada, idioma: Idioma) -> str:
    """Identifica a transação na língua da resposta: onde (ou o tipo), quanto e quando."""
    if t.merchant_name:
        onde = f"{PREPOSICAO[idioma]} {t.merchant_name}"
    else:
        onde = TIPO_DE_TRANSACAO.get(t.transaction_type or "", {}).get(idioma, "")
    return f"{onde} de {valor(t.amount, t.currency)} ({t.transaction_date:%d/%m/%Y})".lstrip()


# Cartão dito ao cliente: o tipo e os 4 últimos dígitos (o número inteiro nem sai da curada).
TIPO_DE_CARTAO: dict[str, dict[Idioma, str]] = {
    "Tarjeta Crédito": {"es": "tarjeta de crédito", "pt": "cartão de crédito"},
    "Tarjeta Débito": {"es": "tarjeta de débito", "pt": "cartão de débito"},
}
FINAL_DO_CARTAO: dict[Idioma, str] = {"es": "terminada en", "pt": "final"}
# Bloqueio simulado (PRD-007): o tipo vem do dispositivo da sessão e é sempre rotulado.
TIPO_DE_BLOQUEIO: dict[str, dict[Idioma, str]] = {
    "preventivo": {"es": "bloqueo preventivo simulado", "pt": "bloqueio preventivo simulado"},
    "completo": {"es": "bloqueo completo simulado", "pt": "bloqueio completo simulado"},
}


def descrever_cartao(produto: str, ultimos4: str | None, idioma: Idioma) -> str:
    """O cartão na língua da resposta: o tipo e o final, quando a base tem o número."""
    tipo = TIPO_DE_CARTAO[produto][idioma]
    return tipo if ultimos4 is None else f"{tipo} {FINAL_DO_CARTAO[idioma]} {ultimos4}"


def marcadores(clausula: str, idioma: Idioma) -> set[str]:
    return {nome for _, nome, _, _ in Formatter().parse(CLAUSULAS[clausula][idioma]) if nome}


def compor(clausula: str, idioma: Idioma, **fatos: str) -> str:
    """Preenche a cláusula aprovada; faltar ou sobrar marcador é erro, não texto improvisado."""
    esperados = marcadores(clausula, idioma)
    if set(fatos) != esperados:
        raise ValueError(f"{clausula}: marcadores {sorted(esperados)}, recebidos {sorted(fatos)}")
    return CLAUSULAS[clausula][idioma].format(**fatos)
