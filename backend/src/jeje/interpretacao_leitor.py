"""Interpretação com o leitor e5 (INTERPRETADOR=leitor), atrás do mesmo contrato do baseline.

Cascata (README, ACH-028): as regras leem primeiro; o leitor só é consultado quando elas não
entendem a mensagem (`entendida`: intenção desconhecida, sem pista e sem sinal de segurança). Ele
só preenche intenção e status, e só com confiança calibrada de pelo menos LEITOR_LIMITE (0,8):
abaixo disso a mensagem segue como não entendida e a conversa pede de novo, como sem ele. Sim/não,
identificador digitado, valor, data, comércio, fraude por palavra e pedido de atendente continuam
das regras, e quem decide o que fazer é a política. Leitor indisponível (artefato ausente, pesos que
não conferem) ou falha ao ler → vale a leitura das regras, com o motivo registrado no trace.

O leitor roda na CPU do próprio processo (~15 ms por mensagem, nenhuma chamada de rede); a carga
(pesos do e5 e artefato) é pedida ao iniciar a API, em segundo plano.

Com o LLM do "não entendi" (INTERPRETADOR=leitor_modelo, DEV-042, jeje.nao_entendi), a mensagem que
o leitor não decide vai a ele antes de terminar não entendida, com o vetor do e5 já calculado.
"""

import contextlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np

from jeje import eventos
from jeje.interpretacao import Interpretacao, interpretar, reconhecivel
from jeje.interpretacao_modelo import Chamada, Leitura, entendida
from jeje.leitor.codificador import E5, Codificador
from jeje.leitor.fluxos import LEITURA_DO_FLUXO
from jeje.leitor.modelo import Leitura as LidaDoModelo
from jeje.leitor.modelo import ModeloLeitor
from jeje.mensagens import Idioma
from jeje.nao_entendi import NaoEntendi

log = logging.getLogger("jeje.leitor")

SEM_PALAVRA_CONHECIDA = "regras (sem palavra conhecida)"

Carregador = Callable[[], tuple[ModeloLeitor, Codificador]]


def dos_arquivos(modelo: Path, e5: Path) -> Carregador:
    """Carga do artefato treinado no build e dos pesos do e5 conferidos (imagem da API)."""

    def carregar() -> tuple[ModeloLeitor, Codificador]:
        codificar = E5(e5)
        codificar.carregar()
        return ModeloLeitor.carregar(modelo), codificar

    return carregar


def em_cascata(
    regras: Interpretacao, lida: LidaDoModelo, limite: float
) -> tuple[Interpretacao, bool]:
    """A leitura final de uma mensagem que as regras não entenderam, dada a do leitor: com confiança
    de pelo menos `limite`, intenção e status do fluxo; abaixo, a das regras. O fluxo lido fica nos
    sinais nos dois casos (auditoria). Devolve (leitura, se o leitor decidiu). A API e a avaliação
    (`jeje.avaliacao_leitor`) decidem por aqui."""
    sinais = (f"leitor:{lida.fluxo}:{lida.confianca:.2f}",)
    if lida.confianca < limite:
        return replace(regras, sinais=sinais), False
    intencao, status = LEITURA_DO_FLUXO[lida.fluxo]
    return replace(regras, intencao=intencao, status=status, sinais=sinais), True


class Leitor:
    """Interpretador em cascata com o leitor e, se houver, o LLM do "não entendi". A carga acontece
    uma vez só: turnos que chegam durante ela esperam; se ela falhar, todo turno segue pelas regras
    com o motivo."""

    def __init__(
        self, carregador: Carregador, limite: float, nao_entendi: NaoEntendi | None = None
    ):
        self.carregador, self.limite, self.nao_entendi = carregador, limite, nao_entendi
        self._trava = threading.Lock()
        self._pronto: tuple[ModeloLeitor, Codificador] | None = None
        self._falha: Exception | None = None

    def _carregado(self) -> tuple[ModeloLeitor, Codificador]:
        with self._trava:
            if self._pronto is None and self._falha is None:
                inicio = time.perf_counter()
                try:
                    self._pronto = self.carregador()
                except Exception as erro:
                    # Fronteira da carga (arquivos, pesos, bibliotecas): uma falha só, lembrada; os
                    # turnos seguem pelas regras em vez de tentar carregar 1 GB a cada mensagem.
                    self._falha = erro
                    log.warning("leitor indisponivel erro=%s", type(erro).__name__)
                else:
                    log.info(
                        "leitor pronto versao=%s ms=%.0f",
                        self._pronto[0].versao[:12],
                        eventos.desde(inicio),
                    )
            if self._falha is not None:
                raise self._falha
            return self._pronto

    def carregar(self, timeout_s: float) -> None:
        """Carga ao iniciar a API (em segundo plano); falha só vira aviso no log."""
        # A falha já foi registrada em _carregado; os turnos seguem pelas regras.
        with contextlib.suppress(Exception):
            self._carregado()
        if self.nao_entendi is not None:
            self.nao_entendi.carregar(timeout_s)

    def __call__(self, texto: str, idioma_anterior: Idioma, referencia: date) -> Leitura:
        regras = interpretar(texto, idioma_anterior, referencia)
        if entendida(regras):
            return Leitura(regras, "regras")
        if not reconhecivel(texto):
            # Ruído segue não entendido, sem o leitor nem o LLM (ACH-122).
            return Leitura(regras, SEM_PALAVRA_CONHECIDA)
        inicio = time.perf_counter()
        try:
            modelo, codificar = self._carregado()
            vetores = codificar([texto])
            (lida,) = modelo.ler_vetores(vetores)
        except Exception as erro:
            # Fronteira do modelo: qualquer falha ao ler vale a leitura das regras.
            return Leitura(
                regras, f"regras (fallback: {type(erro).__name__})", self._chamada(inicio)
            )
        lido, decidiu = em_cascata(regras, lida, self.limite)
        if not decidiu and self.nao_entendi is not None:
            # Terminaria em "não entendi": antes, o LLM com os exemplos (DEV-042).
            return self.nao_entendi(lido, texto, vetores[0], inicio)
        fonte = f"leitor:e5@{modelo.versao[:12]}" if decidiu else "regras (leitor abaixo do limite)"
        return Leitura(lido, fonte, self._chamada(inicio), vetores[0])

    def vetor(self, texto: str) -> np.ndarray:
        """O vetor do e5 de uma mensagem que as regras entenderam (a garantia de fraude o usa)."""
        _, codificar = self._carregado()
        return codificar([texto])[0]

    @staticmethod
    def _chamada(inicio: float) -> Chamada:
        # O leitor não é um modelo de linguagem: nenhum token (custo conhecido, zero).
        return Chamada(eventos.desde(inicio), 0, 0)
