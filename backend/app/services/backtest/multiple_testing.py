from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist, mean

PRODUCTION_SHARPE_GATE = 1.0
PRODUCTION_PVALUE_GATE = 0.05
_NORMAL = NormalDist()
_EULER_GAMMA = 0.5772156649015329


@dataclass(frozen=True, slots=True)
class DeflatedSharpeResult:
    raw_sharpe: float
    deflated_sharpe: float
    deflated_pvalue: float
    trials: int
    benchmark_sharpe: float
    standard_error: float
    passed_gate: bool

    def to_dict(self) -> dict:
        return {
            "raw_sharpe": round(self.raw_sharpe, 6),
            "deflated_sharpe": round(self.deflated_sharpe, 6),
            "deflated_pvalue": round(self.deflated_pvalue, 6),
            "trials": self.trials,
            "benchmark_sharpe": round(self.benchmark_sharpe, 6),
            "standard_error": round(self.standard_error, 6),
            "passed_gate": self.passed_gate,
        }


@dataclass(frozen=True, slots=True)
class MultipleTestingDecision:
    index: int
    raw_pvalue: float
    adjusted_pvalue: float
    rejected: bool


def sharpe_ratio(returns: list[float], *, periods_per_year: int = 252) -> float:
    if len(returns) < 2:
        return 0.0
    avg = mean(returns)
    variance = sum((value - avg) ** 2 for value in returns) / (len(returns) - 1)
    if variance <= 0:
        return 0.0
    return avg / math.sqrt(variance) * math.sqrt(periods_per_year)


def deflated_sharpe_ratio(
    *,
    raw_sharpe: float,
    returns_count: int,
    trials: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    periods_per_year: int = 252,
) -> DeflatedSharpeResult:
    effective_count = max(2, returns_count)
    effective_trials = max(1, trials)
    standard_error = sharpe_standard_error(
        raw_sharpe=raw_sharpe,
        returns_count=effective_count,
        skewness=skewness,
        kurtosis=kurtosis,
        periods_per_year=periods_per_year,
    )
    benchmark = expected_max_null_sharpe(
        effective_trials,
        effective_count,
        periods_per_year=periods_per_year,
    )
    z_score = (raw_sharpe - benchmark) / standard_error if standard_error > 0 else 0.0
    pvalue = 1 - _NORMAL.cdf(z_score)
    return DeflatedSharpeResult(
        raw_sharpe=raw_sharpe,
        deflated_sharpe=z_score,
        deflated_pvalue=pvalue,
        trials=effective_trials,
        benchmark_sharpe=benchmark,
        standard_error=standard_error,
        passed_gate=z_score > PRODUCTION_SHARPE_GATE and pvalue < PRODUCTION_PVALUE_GATE,
    )


def sharpe_standard_error(
    *,
    raw_sharpe: float,
    returns_count: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    periods_per_year: int = 252,
) -> float:
    numerator = 1 - skewness * raw_sharpe + ((kurtosis - 1) / 4) * raw_sharpe**2
    return math.sqrt(max(numerator, 1e-9) * periods_per_year / max(1, returns_count - 1))


def expected_max_null_sharpe(
    trials: int,
    returns_count: int,
    *,
    periods_per_year: int = 252,
) -> float:
    if trials <= 1:
        return 0.0
    first = _NORMAL.inv_cdf(1 - 1 / trials)
    second = _NORMAL.inv_cdf(1 - 1 / (trials * math.e))
    expected_max_normal = (1 - _EULER_GAMMA) * first + _EULER_GAMMA * second
    return expected_max_normal * math.sqrt(periods_per_year / max(1, returns_count - 1))


def bonferroni_correction(
    pvalues: list[float],
    *,
    alpha: float = PRODUCTION_PVALUE_GATE,
) -> list[MultipleTestingDecision]:
    total = max(1, len(pvalues))
    return [
        MultipleTestingDecision(
            index=index,
            raw_pvalue=pvalue,
            adjusted_pvalue=min(1.0, pvalue * total),
            rejected=min(1.0, pvalue * total) <= alpha,
        )
        for index, pvalue in enumerate(pvalues)
    ]


def benjamini_hochberg_fdr(
    pvalues: list[float],
    *,
    alpha: float = PRODUCTION_PVALUE_GATE,
) -> list[MultipleTestingDecision]:
    total = len(pvalues)
    if total == 0:
        return []

    ranked = sorted(enumerate(pvalues), key=lambda item: item[1])
    cutoff_rank = 0
    for rank, (_, pvalue) in enumerate(ranked, start=1):
        if pvalue <= (rank / total) * alpha:
            cutoff_rank = rank

    adjusted_by_index: dict[int, float] = {}
    running_min = 1.0
    for rank, (index, pvalue) in reversed(list(enumerate(ranked, start=1))):
        adjusted = min(running_min, pvalue * total / rank)
        running_min = adjusted
        adjusted_by_index[index] = min(1.0, adjusted)

    rejected = {index for index, _ in ranked[:cutoff_rank]}
    return [
        MultipleTestingDecision(
            index=index,
            raw_pvalue=pvalue,
            adjusted_pvalue=adjusted_by_index[index],
            rejected=index in rejected,
        )
        for index, pvalue in enumerate(pvalues)
    ]
