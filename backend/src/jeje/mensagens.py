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

ESTADO: dict[Status, dict[Idioma, str]] = {
    "Approved": {"es": "aprobada", "pt": "aprovada"},
    "Declined": {"es": "rechazada", "pt": "recusada"},
    "Pending": {"es": "pendiente", "pt": "pendente"},
    "Reversed": {"es": "revertida", "pt": "estornada"},
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


def valor(quantia: Decimal, moeda: str) -> str:
    """Sempre duas casas, milhar com ponto e decimal com vírgula (igual nas duas línguas)."""
    inteiro, _, centavos = f"{quantia:,.2f}".partition(".")
    return f"{moeda} {inteiro.replace(',', '.')},{centavos}"


PREPOSICAO: dict[Idioma, str] = {"es": "en", "pt": "em"}


def descrever(t: TransacaoVerificada, idioma: Idioma) -> str:
    """Identifica a transação na língua da resposta: onde, quanto e quando (fatos da curada)."""
    onde = f"{PREPOSICAO[idioma]} {t.merchant_name}" if t.merchant_name else t.transaction_id
    return f"{onde} de {valor(t.amount, t.currency)} ({t.transaction_date:%d/%m/%Y})"


def marcadores(clausula: str, idioma: Idioma) -> set[str]:
    return {nome for _, nome, _, _ in Formatter().parse(CLAUSULAS[clausula][idioma]) if nome}


def compor(clausula: str, idioma: Idioma, **fatos: str) -> str:
    """Preenche a cláusula aprovada; faltar ou sobrar marcador é erro, não texto improvisado."""
    esperados = marcadores(clausula, idioma)
    if set(fatos) != esperados:
        raise ValueError(f"{clausula}: marcadores {sorted(esperados)}, recebidos {sorted(fatos)}")
    return CLAUSULAS[clausula][idioma].format(**fatos)
