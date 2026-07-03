"""Cross-sectional factor predictivity probe (information coefficient).

Both single-rule families (directional momentum/price_gap, relative-value spread
MR) showed no edge once artifacts/roll-bias were removed. Before building a full
ML prediction head (Track B), probe whether ANY continuous feature has
cross-sectional forward-return predictivity: each day, rank the commodities by a
feature and measure the Spearman rank correlation (IC) with the next-h-day
return. A consistent IC with a high t-stat over thousands of days is a real,
tradable factor; an IC of ~0 means the feature set is dead and a model won't
help.

Spearman (rank) IC is naturally robust to the contract-roll magnitude artifacts
that wrecked the earlier mean-based metrics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ICResult:
    feature: str
    horizon: int
    n_days: int
    mean_ic: float
    ic_std: float
    t_stat: float
    pct_positive: float

    @property
    def is_significant(self) -> bool:
        # |t| > 3 over thousands of days is a robust factor; pair with |IC| size.
        return abs(self.t_stat) > 3.0 and abs(self.mean_ic) >= 0.01

    def to_dict(self) -> dict:
        return {
            "feature": self.feature,
            "horizon": self.horizon,
            "n_days": self.n_days,
            "mean_ic": round(self.mean_ic, 5),
            "ic_std": round(self.ic_std, 5),
            "t_stat": round(self.t_stat, 3),
            "pct_positive": round(self.pct_positive, 4),
            "is_significant": self.is_significant,
        }


def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2 + 1  # 1-based average rank for ties
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    rx = _average_ranks(xs)
    ry = _average_ranks(ys)
    n = len(rx)
    mean_x = sum(rx) / n
    mean_y = sum(ry) / n
    cov = sum((rx[i] - mean_x) * (ry[i] - mean_y) for i in range(n))
    var_x = sum((value - mean_x) ** 2 for value in rx)
    var_y = sum((value - mean_y) ** 2 for value in ry)
    if var_x <= 0 or var_y <= 0:
        return None
    return cov / math.sqrt(var_x * var_y)


def daily_cross_sectional_ic(
    feature_by_symbol: dict[str, float | None],
    forward_by_symbol: dict[str, float | None],
) -> float | None:
    common = [
        symbol
        for symbol in feature_by_symbol
        if symbol in forward_by_symbol
        and feature_by_symbol[symbol] is not None
        and forward_by_symbol[symbol] is not None
    ]
    if len(common) < 3:
        return None
    xs = [float(feature_by_symbol[symbol]) for symbol in common]  # type: ignore[arg-type]
    ys = [float(forward_by_symbol[symbol]) for symbol in common]  # type: ignore[arg-type]
    return spearman(xs, ys)


def aggregate_ic(feature: str, horizon: int, daily_ics: list[float | None]) -> ICResult:
    ics = [ic for ic in daily_ics if ic is not None]
    n = len(ics)
    if n == 0:
        return ICResult(feature, horizon, 0, 0.0, 0.0, 0.0, 0.0)
    mean = sum(ics) / n
    variance = sum((ic - mean) ** 2 for ic in ics) / (n - 1) if n > 1 else 0.0
    std = math.sqrt(variance)
    t_stat = mean / std * math.sqrt(n) if std > 0 else 0.0
    pct_positive = sum(1 for ic in ics if ic > 0) / n
    return ICResult(feature, horizon, n, mean, std, t_stat, pct_positive)
