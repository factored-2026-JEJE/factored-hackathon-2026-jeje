"""Qual transação o cliente descreve, quando o filtro exato não acha nenhuma (DEV-037; NOV-09 e
NOV-06 da validação).

O filtro exato (`politica.resolver_transacao`) só aceita a candidata que bate com todas as pistas, e
continua valendo primeiro: o que ele acha, uma ou várias, segue como antes. Quando ele não acha
nenhuma (um valor dito de cabeça, uma data errada por um dia), as transações do próprio cliente que
podem ser a descrita ganham uma probabilidade pelo ranking (logit condicional), e o conjunto
conformal (LAC) diz quando uma delas é a certa com garantia:

- uma no conjunto: segue com ela (a confirmação antes do pré-caso não muda);
- sem essa garantia: mostra as possíveis, da mais para a menos provável; até três viram botões,
  mais viram a pergunta pelo campo que mais as divide (ganho de informação, NOV-06);
- nenhuma possível: pede dados, como antes.

Os pesos e o limiar vêm de uma calibração fora da conversa (`python -m
jeje.calibrar_qual_transacao`), com o limiar medido só nos casos em que o filtro exato não acha
nada, num arquivo versionado que só tem agregados: nenhum registro de cliente.
"""

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from jeje.politica import Candidata, Pista, Resolucao

ATRIBUTOS = ("valor_perto", "valor_igual", "data_dentro", "data_distancia", "comercio", "recencia")
# Campos que a pergunta pode pedir, na ordem de desempate; o valor de cada um numa candidata.
CAMPOS: dict[str, Callable[[Candidata], object]] = {
    "data": lambda c: c.transaction_date.date(),
    "valor": lambda c: c.amount,
    "comercio": lambda c: c.merchant_name or "",
}
OPCOES_NA_TELA = 3


def tem_pista(pista: Pista) -> bool:
    return any(p is not None for p in (pista.valor, pista.data, pista.comercio))


def concorda(candidata: Candidata, pista: Pista) -> bool:
    """A candidata pode ser a descrita: do comércio citado, quando o cliente cita um (ele disse o
    nome; valor e data é que se dizem de cabeça); sem comércio, com o valor a até 10% ou a data a
    até 7 dias. Só essas entram no ranking: sem nenhuma, a resposta é pedir dados."""
    if pista.comercio is not None:
        return candidata.merchant_name == pista.comercio
    valor = (
        pista.valor is not None
        and pista.valor > 0
        and abs(math.log(max(float(candidata.amount), 1e-6) / float(pista.valor))) <= 0.10
    )
    dias = (
        None if pista.data is None else abs((candidata.transaction_date.date() - pista.data).days)
    )
    return valor or (dias is not None and dias <= 7)


def elegiveis(candidatas: Sequence[Candidata], pista: Pista) -> list[int]:
    return [i for i, c in enumerate(candidatas) if concorda(c, pista)]


def atributos(candidatas: Sequence[Candidata], pista: Pista, hoje: date) -> np.ndarray:
    """Uma linha por candidata: quanto ela concorda com cada pista (0 quando a pista não veio) e
    quão recente ela é."""
    linhas = []
    for c in candidatas:
        dia = c.transaction_date.date()
        valor_perto = valor_igual = data_dentro = data_distancia = 0.0
        if pista.valor is not None and pista.valor > 0:
            razao = abs(math.log(max(float(c.amount), 1e-6) / float(pista.valor)))
            valor_perto = max(-razao / 0.01, -20.0)
            valor_igual = float(abs(c.amount - pista.valor) <= 0.01)
        if pista.data is not None:
            dias = abs((dia - pista.data).days)
            data_dentro = float(dias == 0)
            data_distancia = -min(dias, 60) / 7
        comercio = float(pista.comercio is not None and c.merchant_name == pista.comercio)
        recencia = -min(max((hoje - dia).days, 0), 365) / 30
        linhas.append([valor_perto, valor_igual, data_dentro, data_distancia, comercio, recencia])
    return np.array(linhas, dtype=float).reshape(len(linhas), len(ATRIBUTOS))


def probabilidades(x: np.ndarray, pesos: np.ndarray) -> np.ndarray:
    s = x @ pesos
    s = s - s.max()
    e = np.exp(s)
    return e / e.sum()


def treinar(casos: Sequence[tuple[np.ndarray, int]], l2: float = 0.01) -> np.ndarray:
    """Pesos do logit condicional: maximiza a probabilidade da certa entre as candidatas de cada
    caso (L-BFGS, com penalidade L2)."""
    from scipy.optimize import minimize  # só a calibração usa

    def custo(w: np.ndarray) -> tuple[float, np.ndarray]:
        total, gradiente = 0.0, np.zeros_like(w)
        for x, certa in casos:
            p = probabilidades(x, w)
            total -= math.log(max(p[certa], 1e-300))
            gradiente += p @ x - x[certa]
        n = len(casos)
        return total / n + l2 * float(w @ w), gradiente / n + 2 * l2 * w

    inicio = np.zeros(len(ATRIBUTOS))
    return minimize(custo, inicio, jac=True, method="L-BFGS-B").x


def limiar(escores: Sequence[float], alfa: float) -> float:
    """Quantil conformal com a correção de amostra finita: o escore da posição
    teto((n + 1)(1 - alfa))."""
    ordenados = sorted(escores)
    k = math.ceil((len(ordenados) + 1) * (1 - alfa))
    return ordenados[min(k, len(ordenados)) - 1]


@dataclass(frozen=True)
class Calibracao:
    versao: str
    alfa: float
    pesos: tuple[float, ...]
    limiares: dict[str, float]  # por idioma: o conjunto guarda as com 1 - p ≤ limiar

    @classmethod
    def carregar(cls, caminho: Path) -> "Calibracao":
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        pesos = tuple(dados["pesos"][nome] for nome in ATRIBUTOS)
        return cls(dados["versao"], dados["alfa"], pesos, dict(dados["limiares"]))

    def ordem(self, x: np.ndarray, aceitas: Sequence[int]) -> list[tuple[int, float]]:
        """As candidatas aceitas com a probabilidade entre elas, da mais para a menos provável."""
        p = probabilidades(x[list(aceitas)], np.array(self.pesos))
        return sorted(zip(aceitas, p.tolist(), strict=True), key=lambda par: -par[1])

    def conjunto(self, x: np.ndarray, idioma: str, aceitas: Sequence[int]) -> list[int]:
        """As que podem ser a certa (LAC: 1 - p até o limiar), da mais para a menos provável."""
        return [i for i, p in self.ordem(x, aceitas) if 1 - p <= self.limiares[idioma]]


def campo_que_mais_divide(
    candidatas: Sequence[Candidata],
    pesos: np.ndarray,
    conjunto: Sequence[int],
    ja_ditos: frozenset[str] = frozenset(),
) -> str | None:
    """O campo cuja resposta mais divide o conjunto: a maior entropia da probabilidade agrupada
    pelo valor do campo (NOV-06), fora os que o cliente já disse. Nenhum campo divide → None."""

    def entropia(campo: str) -> float:
        massa: dict[object, float] = {}
        for i in conjunto:
            chave = CAMPOS[campo](candidatas[i])
            massa[chave] = massa.get(chave, 0.0) + float(pesos[i])
        total = sum(massa.values())
        return -sum(m / total * math.log(m / total) for m in massa.values() if m > 0)

    livres = [campo for campo in CAMPOS if campo not in ja_ditos]
    entropias = {campo: entropia(campo) for campo in livres}
    melhor = max(livres, key=lambda campo: entropias[campo], default=None)
    return melhor if melhor is not None and entropias[melhor] > 0 else None


def resolver(
    candidatas: Sequence[Candidata],
    pista: Pista,
    calibracao: Calibracao,
    idioma: str,
    hoje: date,
    maximo_opcoes: int,
) -> Resolucao:
    """A mesma resposta do filtro exato, entre as candidatas que podem ser a descrita: com uma só
    no conjunto conformal e uma pista que não engana (o valor marcado, a data, o comércio ou "a
    última"), segue com ela; sem essa garantia (o conjunto vazio ou com várias, ou só o número
    solto), mostra as possíveis, da mais para a menos provável: até três viram botões, mais viram
    a pergunta pelo campo que mais as divide. Nenhuma possível pede dados. "A última" escolhe a
    mais recente, como no filtro."""
    aceitas = elegiveis(candidatas, pista)
    if not aceitas:
        return Resolucao("nenhuma", ())
    x = atributos(candidatas, pista, hoje)
    ordem = calibracao.ordem(x, aceitas)
    conjunto = calibracao.conjunto(x, idioma, aceitas)
    if pista.ultima:
        conjunto = [min(aceitas)]  # as candidatas vêm das mais recentes para as mais antigas
    # Seguir direto pede uma pista que não engana: o número solto pode ser o dia ou o final do
    # cartão (ACH-143), e a transação perto dele vira opção.
    direta = (
        pista.valor_marcado or pista.ultima or pista.data is not None or pista.comercio is not None
    )
    if len(conjunto) != 1 or not direta:
        conjunto = [i for i, _ in ordem]  # sem garantia de uma só: as possíveis
    ids = tuple(candidatas[i].transaction_id for i in conjunto)
    if len(conjunto) == 1 and direta:
        return Resolucao("unica", ids)
    if len(conjunto) <= OPCOES_NA_TELA:
        return Resolucao("varias", ids)
    pesos = np.zeros(len(candidatas))
    for i, p in ordem:
        pesos[i] = p
    ditos = {"valor": pista.valor, "data": pista.data, "comercio": pista.comercio}
    ja_ditos = frozenset(nome for nome, dito in ditos.items() if dito is not None)
    campo = campo_que_mais_divide(candidatas, pesos, conjunto, ja_ditos)
    return Resolucao("varias", ids[:maximo_opcoes], campo=campo)
