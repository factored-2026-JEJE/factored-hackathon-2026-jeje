"""Exemplos do BANKING77 para o LLM do "não entendi" (DEV-042; NOV-10 e NOV-19 da validação).

Quando nem as regras nem o leitor entendem a mensagem, o LLM lê com exemplos no prompt: as 3 frases
de treino mais parecidas com ela, de cada intenção, no idioma dela. O build salva as frases ES e PT
do treino oficial do BANKING77 com a intenção e o vetor do e5 (os mesmos que o treino do leitor
calcula); a conversa só compara o vetor da mensagem com eles. O teste do BANKING77 nunca entra.

O rótulo é o que a validação pré-registrou para comparar intérpretes (`validacao/rotulos.py`, usado
no NOV-10 e no NOV-19), não o fluxo do leitor: o prompt foi escrito e medido com ele. Intenções que
cabem em mais de uma leitura (pedido de reembolso, tarifa, câmbio, celular perdido...) ficam fora;
as que não são do atendimento são fora de escopo.
"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

from jeje.leitor.codificador import Codificador
from jeje.leitor.corpus import Exemplo

INTENCAO_DO_BANKING77 = {
    **dict.fromkeys(
        ("declined_card_payment", "declined_cash_withdrawal", "declined_transfer",
         "pending_card_payment", "pending_cash_withdrawal", "pending_transfer",
         "reverted_card_payment?", "failed_transfer"),
        "consultar",
    ),
    **dict.fromkeys(
        ("card_payment_not_recognised", "cash_withdrawal_not_recognised",
         "direct_debit_payment_not_recognised", "transaction_charged_twice"),
        "contestar",
    ),
    **dict.fromkeys(("compromised_card", "lost_or_stolen_card"), "fraude"),
}  # fmt: skip
AMBIGUAS = frozenset({
    # contestar, consultar ou fora: pedem reembolso ou discordam de valor ou tarifa
    "request_refund", "extra_charge_on_statement", "card_payment_wrong_exchange_rate",
    "wrong_amount_of_cash_received", "wrong_exchange_rate_for_cash_withdrawal",
    "card_payment_fee_charged", "cash_withdrawal_charge", "transfer_fee_charged",
    # consultar ou fora: saldo, recarga ou transferência, não uma compra
    "Refund_not_showing_up", "balance_not_updated_after_bank_transfer",
    "balance_not_updated_after_cheque_or_cash_deposit", "transfer_not_received_by_recipient",
    "pending_top_up", "top_up_failed", "top_up_reverted",
    # fraude ou fora: celular perdido, cartão retido no caixa
    "lost_or_stolen_phone", "card_swallowed",
})  # fmt: skip
# Na ordem em que entram no prompt (a da validação: alfabética).
INTENCOES = ("consultar", "contestar", "fora_de_escopo", "fraude")
IDIOMAS = ("es", "pt")
K = 3


class VizinhosInvalidos(Exception):
    """Artefato ausente, de outro formato ou sem alguma intenção de algum idioma."""


def intencao(rotulo: str) -> str | None:
    """A intenção de uma frase do BANKING77 pelo rótulo do corpus; None quando é ambígua."""
    if rotulo in AMBIGUAS:
        return None
    return INTENCAO_DO_BANKING77.get(rotulo, "fora_de_escopo")


def versao(versao_do_leitor: str) -> str:
    """O leitor fixa os dados e os pesos do e5; o rótulo das frases é o resto."""
    entrada = {
        "leitor": versao_do_leitor,
        "rotulos": [INTENCAO_DO_BANKING77, sorted(AMBIGUAS)],
    }
    return hashlib.sha256(json.dumps(entrada, sort_keys=True).encode()).hexdigest()


@dataclass
class Vizinhos:
    textos: dict[tuple[str, str], list[str]]  # (idioma, intenção) → frases, na ordem do corpus
    vetores: dict[tuple[str, str], np.ndarray]  # (idioma, intenção) → vetores do e5 das frases
    versao: str

    FORMATO = 1

    @classmethod
    def dos_exemplos(
        cls, exemplos: Iterable[Exemplo], codificar: Codificador, versao_: str
    ) -> "Vizinhos":
        textos: dict[tuple[str, str], list[str]] = {}
        for e in exemplos:
            if e.origem != "banking77" or e.idioma not in IDIOMAS:
                continue
            if (lida := intencao(e.intencao)) is not None:
                textos.setdefault((e.idioma, lida), []).append(e.texto)
        vizinhos = cls(textos, {chave: codificar(t) for chave, t in textos.items()}, versao_)
        vizinhos._conferir()
        return vizinhos

    def mais_parecidos(self, vetor: np.ndarray, idioma: str, k: int = K) -> dict[str, list[str]]:
        """As `k` frases mais parecidas com a mensagem de cada intenção, da mais parecida para a
        menos (vetores normalizados: o produto escalar é o cosseno)."""
        saida = {}
        for lida in INTENCOES:
            chave = (idioma, lida)
            ordem = np.argsort(-(self.vetores[chave] @ vetor), kind="stable")[:k]
            saida[lida] = [self.textos[chave][j] for j in ordem]
        return saida

    def _conferir(self) -> None:
        for chave in ((i, lida) for i in IDIOMAS for lida in INTENCOES):
            if not self.textos.get(chave):
                raise VizinhosInvalidos(f"sem frases de {chave[1]} em {chave[0]}")
            vetores = self.vetores.get(chave)
            if vetores is None or len(vetores) != len(self.textos[chave]):
                raise VizinhosInvalidos(f"frases e vetores de {chave} não batem")

    def salvar(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"formato": self.FORMATO, "textos": self.textos, "vetores": self.vetores,
                     "versao": self.versao}, caminho)  # fmt: skip

    @classmethod
    def carregar(cls, caminho: Path) -> "Vizinhos":
        # Artefato produzido pelo próprio build (joblib/pickle): nunca carregar de origem externa.
        if not caminho.is_file():
            raise VizinhosInvalidos(f"artefato ausente: {caminho}")
        conteudo = joblib.load(caminho)
        if not isinstance(conteudo, dict) or conteudo.get("formato") != cls.FORMATO:
            raise VizinhosInvalidos(f"formato desconhecido em {caminho}")
        vizinhos = cls(conteudo["textos"], conteudo["vetores"], conteudo["versao"])
        vizinhos._conferir()
        return vizinhos
