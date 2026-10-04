"""Garantia de encaminhamento da fraude (DEV-046): a V3 do NOV-33 da validação, depois da cascata.

Com INTERPRETADOR=leitor_modelo e GARANTIA_DE_FRAUDE ligada, a mensagem que a cascata não leu como
fraude nem como pedido de atendente (e que não é um sim, um não, uma escolha ou outro controle da
conversa) passa por três passos:

1. o detector (jeje.leitor.garantia), treinado no build sobre os vetores do e5, dispara com
   p(fraude) maior ou igual ao limiar do idioma;
2. sinal de prevenção sem vítima segura a mensagem (as listas do NOV-33, sem os marcadores de
   suspeita, EV-222): quem só pergunta como se proteger não vai ao atendente por aqui;
3. o LLM do "não entendi" (o mesmo prompt AL9, com os mesmos exemplos) confirma: lê fraude ou
   pedido de atendente. Se ele já leu a mensagem na cascata, vale essa leitura.

Passando os três, a conversa encaminha ao atendente como possível fraude, sem bloquear o cartão
(jeje.conversa). Sem o LLM, ou se ele falhar, a garantia não dispara (NOV-39): a mensagem segue a
cascata. Sempre que o detector dispara, o sinal da garantia (p, limiar, prevenção e o que o LLM leu)
vai para a leitura e, dali, para o trace do turno.
"""

import contextlib
import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date

import numpy as np

from jeje import eventos
from jeje.interpretacao import Interpretacao, normalizar
from jeje.interpretacao_leitor import SEM_PALAVRA_CONHECIDA, Leitor
from jeje.interpretacao_modelo import SINAL_DA_GARANTIA, Chamada, Leitura
from jeje.leitor.garantia import Garantia
from jeje.mensagens import Idioma
from jeje.nao_entendi import NaoEntendi

log = logging.getLogger("jeje.garantia")

# As listas do NOV-33 (experimentos/nov_33_relato.py), sem os marcadores de suspeita ("es golpe",
# "e uma fraude"...): a suspeita sem prejuízo vai ao atendente (PRD-010, EV-222).
PREVENCAO = ("evitar", "no caer", "nao cair", "como me protejo", "como me proteger", "dicas",
             "consejos", "medo de", "miedo de", "prevenir", "proteger")  # fmt: skip
VITIMA = ("cai", "me aplicaron", "sofri", "me estafaron", "fui vitima", "fui victima", "perdi",
          "me robaron", "roubaram", "transferi", "hice una transferencia", "fiz um pix",
          "fiz uma transferencia", "me sacaron", "tiraram", "me quitaron", "apareceram",
          "aparecieron")  # fmt: skip
ENCAMINHAM = ("fraude", "humano")

Carregador = Callable[[], Garantia]


def _tem(limpo: str, termos: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(t)}\b", limpo) for t in termos)


def so_prevencao(texto: str) -> bool:
    """Sinal de prevenção sem nenhum de vítima (o passo 2)."""
    limpo = normalizar(texto)
    return _tem(limpo, PREVENCAO) and not _tem(limpo, VITIMA)


@dataclass(frozen=True)
class Decisao:
    p: float
    limiar: float
    prevencao: bool = False
    llm: str | None = None  # o que o LLM leu; None se não foi chamado
    erro: str | None = None  # a classe do erro, se o LLM falhou

    @property
    def detector(self) -> bool:
        return self.p >= self.limiar

    @property
    def dispara(self) -> bool:
        return self.detector and not self.prevencao and self.llm in ENCAMINHAM

    @property
    def sinal(self) -> str:
        """O rastro no trace: "garantia:p=0.73:limiar=0.58:llm=fraude:dispara"."""
        partes = [f"p={self.p:.2f}", f"limiar={self.limiar:.2f}"]
        if self.prevencao:
            partes.append("prevencao")
        if self.llm is not None:
            partes.append(f"llm={self.llm}")
        if self.erro is not None:
            partes.append(f"erro={self.erro}")
        partes.append("dispara" if self.dispara else "segue")
        return ":".join([SINAL_DA_GARANTIA, *partes])


class GarantiaDeFraude:
    """Os três passos sobre o vetor da mensagem. O detector é carregado uma vez só; se a carga
    falhar, a garantia não roda (a mensagem segue a cascata), com o motivo no log."""

    def __init__(self, carregador: Carregador, llm: NaoEntendi):
        self.carregador, self.llm = carregador, llm
        self._trava = threading.Lock()
        self._pronto: Garantia | None = None
        self._falha: Exception | None = None

    def _carregado(self) -> Garantia:
        with self._trava:
            if self._pronto is None and self._falha is None:
                try:
                    self._pronto = self.carregador()
                except Exception as erro:
                    # Fronteira do artefato: uma falha só, lembrada (como a do leitor).
                    self._falha = erro
                    log.warning("garantia indisponivel erro=%s", type(erro).__name__)
            if self._falha is not None:
                raise self._falha
            return self._pronto

    def carregar(self, _timeout_s: float) -> None:
        with contextlib.suppress(Exception):
            self._carregado()

    def __call__(
        self, texto: str, idioma: Idioma, vetor: np.ndarray, uso: dict, lido: str | None = None
    ) -> Decisao:
        """A decisão para uma mensagem; `lido` é o que o LLM já leu nela na cascata, se leu."""
        detector = self._carregado()
        p = float(detector.p_fraude(vetor[np.newaxis, :])[0])
        limiar = detector.limiares[idioma]
        if p < limiar:
            return Decisao(p, limiar)
        if so_prevencao(texto):
            return Decisao(p, limiar, prevencao=True)
        if lido is not None:
            return Decisao(p, limiar, llm=lido)
        try:
            return Decisao(p, limiar, llm=self.llm.ler(texto, idioma, vetor, uso))
        # Fronteira externa: sem a confirmação do LLM, a garantia não dispara (NOV-39).
        except Exception as erro:
            log.warning("garantia sem o modelo erro=%s", type(erro).__name__)
            return Decisao(p, limiar, erro=type(erro).__name__)


def controle(lida: Interpretacao) -> bool:
    """Sim, não, escolha, aceite da oferta, outra transação, cortesia, caso ou identificador: a
    mensagem conduz a conversa e não é relato."""
    sinais = (
        lida.aceita_oferta,
        lida.outra,
        lida.caso,
        lida.id_digitado,
        lida.uso_desfeito,
        lida.instrucao,
    )
    pistas = (lida.resposta, lida.escolha, lida.cortesia)
    return any(sinais) or any(p is not None for p in pistas)


class ComGarantia:
    """A cascata com o leitor e o LLM (jeje.interpretacao_leitor) e, no que ela não leu como
    fraude nem atendente, a garantia."""

    def __init__(self, leitor: Leitor, garantia: GarantiaDeFraude):
        self.leitor, self.garantia = leitor, garantia

    def carregar(self, timeout_s: float) -> None:
        self.leitor.carregar(timeout_s)
        self.garantia.carregar(timeout_s)

    def __call__(self, texto: str, idioma_anterior: Idioma, referencia: date) -> Leitura:
        leitura = self.leitor(texto, idioma_anterior, referencia)
        lida = leitura.lida
        if lida.intencao in ENCAMINHAM or controle(lida) or leitura.fonte == SEM_PALAVRA_CONHECIDA:
            return leitura  # o ruído também não chega à garantia (ACH-122)
        inicio, uso = time.perf_counter(), {}
        lido = lida.intencao if leitura.fonte.startswith("ollama:") else None
        try:
            vetor = leitura.vetor if leitura.vetor is not None else self.leitor.vetor(texto)
            decisao = self.garantia(texto, lida.idioma, vetor, uso, lido)
        except Exception as erro:
            # Detector ou e5 indisponíveis: a mensagem segue a cascata.
            log.warning("garantia nao usada erro=%s", type(erro).__name__)
            return leitura
        if not decisao.detector:
            return leitura
        sinais = (*lida.sinais, decisao.sinal)
        chamada = _somada(leitura.chamada, Chamada(eventos.desde(inicio), uso.get("entrada"),
                                                   uso.get("saida")))  # fmt: skip
        if not decisao.dispara:
            return replace(leitura, lida=replace(lida, sinais=sinais), chamada=chamada)
        fraude = replace(lida, intencao="fraude", sinais=sinais)
        fonte = f"{SINAL_DA_GARANTIA}:{self.garantia.llm.ollama.modelo}"
        return Leitura(fraude, fonte, chamada, leitura.vetor)

    def decidir(self, texto: str, idioma: Idioma) -> Decisao:
        """A decisão da garantia para um texto e um idioma, sem a cascata: a mesma dos turnos,
        chamável pelo trabalhador da validação na imagem (aceite da V3)."""
        return self.garantia(texto, idioma, self.leitor.vetor(texto), {})


def _somada(antes: Chamada | None, agora: Chamada) -> Chamada:
    """A chamada do turno com a da garantia: latências somadas, tokens somados quando conhecidos."""
    if antes is None:
        return agora

    def soma(a: int | None, b: int | None) -> int | None:
        return a if b is None else b if a is None else a + b

    return Chamada(antes.latencia_ms + agora.latencia_ms,
                   soma(antes.tokens_entrada, agora.tokens_entrada),
                   soma(antes.tokens_saida, agora.tokens_saida))  # fmt: skip
