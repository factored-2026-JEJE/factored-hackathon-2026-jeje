"""Fluxos do leitor, de onde vêm (BANKING77, MInDS-14) e o que viram na leitura da conversa.

Os rótulos do dataset do desafio não servem de gabarito (42 textos distintos em 171 mil
transcrições; `contact_reason` independente do texto). O gabarito vem de corpora públicos
(CC-BY-4.0): as 77 intenções do BANKING77 e 3 das 14 do MInDS-14 viram os fluxos do atendimento.
O agrupamento é uma decisão do time, não dos datasets; casos de fronteira anotados abaixo.
"""

from typing import Literal

Fluxo = Literal[
    "explicar_recusa",
    "explicar_pendencia",
    "explicar_estorno",
    "ver_transacoes",
    "abrir_disputa",
    "relato_de_fraude",
    "fora_de_escopo",
]
FLUXOS: tuple[Fluxo, ...] = (
    "explicar_recusa",
    "explicar_pendencia",
    "explicar_estorno",
    "ver_transacoes",
    "abrir_disputa",
    "relato_de_fraude",
    "fora_de_escopo",
)

# Intenções do BANKING77 que caem nos fluxos do atendimento; todas as demais são fora_de_escopo.
FLUXO_DO_BANKING77: dict[str, Fluxo] = {
    "declined_card_payment": "explicar_recusa",
    "declined_cash_withdrawal": "explicar_recusa",
    "declined_transfer": "explicar_recusa",
    "pending_card_payment": "explicar_pendencia",
    "pending_cash_withdrawal": "explicar_pendencia",
    "pending_top_up": "explicar_pendencia",
    "pending_transfer": "explicar_pendencia",
    "reverted_card_payment?": "explicar_estorno",
    "top_up_reverted": "explicar_estorno",
    "Refund_not_showing_up": "explicar_estorno",
    "card_payment_not_recognised": "abrir_disputa",
    "cash_withdrawal_not_recognised": "abrir_disputa",
    "direct_debit_payment_not_recognised": "abrir_disputa",
    "transaction_charged_twice": "abrir_disputa",
    # Fronteira: pedir reembolso de uma compra é disputa; reembolso já pedido que não chegou
    # é estorno (Refund_not_showing_up).
    "request_refund": "abrir_disputa",
    "compromised_card": "relato_de_fraude",
    "lost_or_stolen_card": "relato_de_fraude",
    "lost_or_stolen_phone": "relato_de_fraude",
}

# Intenções do MInDS-14 (fala real transcrita) que o BANKING77 não cobre; as outras 11 são
# fora_de_escopo. Fronteira: bloquear o cartão (FREEZE) é tratado como relato de fraude, que vai
# para atendente com a pendência de bloqueio (decisão a confirmar com o time).
FLUXO_DO_MINDS14: dict[str, Fluxo] = {
    "card_issues": "explicar_recusa",
    "freeze": "relato_de_fraude",
    "latest_transactions": "ver_transacoes",
}

# O que cada fluxo vira na leitura da conversa (README, ACH-028): intenção do interpretador
# (jeje.interpretacao.Intencao) e status citado. Aqui sem importar a interpretação: o treino da
# imagem copia só este pacote, e mudar as regras não pode invalidar o cache do treino.
LEITURA_DO_FLUXO: dict[Fluxo, tuple[str, str | None]] = {
    "explicar_recusa": ("consultar", "Declined"),
    "explicar_pendencia": ("consultar", "Pending"),
    "explicar_estorno": ("consultar", "Reversed"),
    "ver_transacoes": ("consultar", None),
    "abrir_disputa": ("contestar", None),
    "relato_de_fraude": ("fraude", None),
    "fora_de_escopo": ("fora_de_escopo", None),
}


def fluxo_do_banking77(intencao: str) -> Fluxo:
    return FLUXO_DO_BANKING77.get(intencao, "fora_de_escopo")


def fluxo_do_minds14(intencao: str) -> Fluxo:
    return FLUXO_DO_MINDS14.get(intencao, "fora_de_escopo")
