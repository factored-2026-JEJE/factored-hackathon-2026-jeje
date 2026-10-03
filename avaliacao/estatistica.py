"""Intervalo exato de Clopper-Pearson pela binomial, só com a biblioteca padrão."""

import math


def _cdf(sucessos: int, total: int, p: float) -> float:
    """P(X <= sucessos) para X ~ Binomial(total, p), em escala logarítmica."""
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 1.0 if sucessos >= total else 0.0
    log_p, log_q = math.log(p), math.log1p(-p)
    base = math.lgamma(total + 1)
    return min(
        1.0,
        sum(
            math.exp(
                base
                - math.lgamma(k + 1)
                - math.lgamma(total - k + 1)
                + k * log_p
                + (total - k) * log_q
            )
            for k in range(sucessos + 1)
        ),
    )


def _bissecao(funcao, alvo: float) -> float:
    """O p em [0, 1] com funcao(p) == alvo, para funcao decrescente em p."""
    baixo, alto = 0.0, 1.0
    for _ in range(200):
        meio = (baixo + alto) / 2
        if funcao(meio) > alvo:
            baixo = meio
        else:
            alto = meio
    return (baixo + alto) / 2


def clopper_pearson(sucessos: int, total: int, confianca: float = 0.95) -> tuple[float, float]:
    """IC exato bilateral de uma proporção; (nan, nan) sem observações."""
    if total == 0:
        return math.nan, math.nan
    cauda = (1 - confianca) / 2
    baixo = 0.0
    if sucessos > 0:
        baixo = _bissecao(lambda p: _cdf(sucessos - 1, total, p), 1 - cauda)
    alto = 1.0
    if sucessos < total:
        alto = _bissecao(lambda p: _cdf(sucessos, total, p), cauda)
    return baixo, alto
