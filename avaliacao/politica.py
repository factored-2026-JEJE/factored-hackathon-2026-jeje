"""Oráculo da contestação (PRD-001 e PRD-008), escrito pela validação a partir do plano.

Recebe a linha curada da fixture e os limites com que a stack subiu, lidos dos arquivos do
compose do commit, e diz se a contestação vira proposta de pré-caso (POL-DISP-01) ou vai ao
atendente. Leituras fixadas pela validação, porque o texto não detalha:

- a noite (POL-HUM-04) vai do início, incluído, ao fim, excluído, pela hora de
  `transaction_date`, e só em App e Web;
- "acima de" é estritamente maior;
- a janela (POL-HUM-05) conta os dias até o "hoje" dos dados: o menor entre o relógio e o último
  dia com transação na base. "Mais de 120 dias" é estritamente maior.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

DIGITAIS = {"App", "Web"}

# Campo de `Limites` → variável do compose.
CHAVES = {
    "pre_caso": "LIMITE_PRE_CASO_USD",
    "noturno": "LIMITE_NOTURNO_USD",
    "noturno_dia": "LIMITE_NOTURNO_DIA_USD",
    "inicio_h": "NOTURNO_INICIO_H",
    "fim_h": "NOTURNO_FIM_H",
    "transferencia": "LIMITE_SEGURANCA_TRANSFERENCIA_USD",
    "janela_dias": "JANELA_CONTESTACAO_DIAS",
    "reincidencia": "REINCIDENCIA_PRE_CASOS",
    "reincidencia_dias": "REINCIDENCIA_DIAS",
}
INTEIROS = {"inicio_h", "fim_h", "janela_dias", "reincidencia", "reincidencia_dias"}


@dataclass(frozen=True)
class Limites:
    pre_caso: Decimal
    noturno: Decimal | None = None
    noturno_dia: Decimal | None = None
    inicio_h: int | None = None
    fim_h: int | None = None
    transferencia: Decimal | None = None
    janela_dias: int | None = None
    reincidencia: int | None = None
    reincidencia_dias: int | None = None


def limites_do_compose(
    produto: Path, arquivos: tuple[str, ...], ajustes: dict[str, str] | None = None
) -> Limites:
    """Os limites dos arquivos do compose, na ordem em que a stack os usa (o último vence), com
    `ajustes` ({variável: valor}) por cima."""
    textos = [(produto / arquivo).read_text() for arquivo in arquivos]
    valores = {}
    for campo, chave in CHAVES.items():
        bruto = (ajustes or {}).get(chave)
        if bruto is None:
            for texto in textos:
                achado = re.search(rf'^\s*{chave}:\s*"?([0-9.]+)"?', texto, re.MULTILINE)
                if achado:
                    bruto = achado[1]
        if bruto is not None:
            valores[campo] = int(bruto) if campo in INTEIROS else Decimal(bruto)
    if "pre_caso" not in valores:
        raise ValueError(f"sem LIMITE_PRE_CASO_USD em {arquivos}")
    return Limites(**valores)


def hoje_dos_dados(linhas: dict[str, dict], relogio: date | None = None) -> date | None:
    """O "hoje" da PRD-008: o menor entre o relógio e o último dia com transação na base."""
    dias = [date.fromisoformat(linha["transaction_date"][:10]) for linha in linhas.values()]
    if not dias:
        return None
    return min(relogio or datetime.now(UTC).date(), max(dias))


def valor_em_dolar(linha: dict) -> Decimal | None:
    if linha["currency"] == "USD":
        return linha["valor"]
    return Decimal(linha["amount_usd"]) if linha.get("amount_usd") else None


def noturna_digital(linha: dict, limites: Limites) -> bool:
    """App ou Web dentro da janela noturna (a janela pode virar a meia-noite)."""
    if limites.inicio_h is None or limites.fim_h is None or linha["channel"] not in DIGITAIS:
        return False
    hora = int(linha["transaction_date"][11:13])
    if limites.inicio_h > limites.fim_h:
        return hora >= limites.inicio_h or hora < limites.fim_h
    return limites.inicio_h <= hora < limites.fim_h


def seguranca(linha: dict, limites: Limites) -> bool:
    """POL-SEG-01: transferência com valor em dólar acima do limite de segurança."""
    usd = valor_em_dolar(linha)
    return (
        limites.transferencia is not None
        and linha["transaction_type"] == "Transfer"
        and usd is not None
        and usd > limites.transferencia
    )


def elegivel(linha: dict, limites: Limites, hoje: date | None = None) -> bool:
    """A contestação desta transação vira proposta de pré-caso (POL-DISP-01): aprovada, dentro
    da janela e dos limites, e fora das regras que mandam ao atendente."""
    if seguranca(linha, limites) or linha["transaction_status"] != "Approved":
        return False
    data = date.fromisoformat(linha["transaction_date"][:10])
    janela = limites.janela_dias
    if janela is not None and hoje is not None and (hoje - data).days > janela:
        return False
    usd = valor_em_dolar(linha)
    if usd is None or usd > limites.pre_caso:
        return False
    noturna = noturna_digital(linha, limites)
    if noturna and limites.noturno is not None and usd > limites.noturno:
        return False
    return not (noturna and limites.noturno_dia is not None and usd > limites.noturno_dia)
