"""Cross-sectional reversal long-short portfolio backtest.

The IC probe found a strong, robust cross-sectional reversal factor (rank by
trailing momentum / distance-from-MA gives a large negative IC, |t| up to 18).
This turns that signal into a tradable P&L: each rebalance, rank the universe
and go LONG the bottom-ranked (losers) / SHORT the top-ranked (winners),
dollar-neutral, hold to the next rebalance, net of turnover cost. Reports
Sharpe / Deflated Sharpe over the 16-year history — the decisive test of whether
the real IC is a real strategy.

Symbol holding-period returns are clipped at |r|>0.5 (contract-roll artifacts)
so a single roll cannot blow up a leg's mean.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.services.backtest.multiple_testing import (
    DeflatedSharpeResult,
    deflated_sharpe_ratio,
    sharpe_ratio,
)
from app.services.backtest.path_metrics import PathMetrics, calculate_path_metrics

MAX_ABS_PERIOD_RETURN = 0.5


@dataclass(frozen=True, slots=True)
class XSBacktestReport:
    signal: str
    quantile_k: int
    periods: int
    gross_mean_return: float | None
    net_mean_return: float | None
    win_rate: float | None
    sharpe: float | None
    deflated: DeflatedSharpeResult | None
    path: PathMetrics | None
    avg_turnover: float | None

    @property
    def has_significant_edge(self) -> bool:
        return self.deflated is not None and self.deflated.passed_gate

    def to_dict(self) -> dict:
        return {
            "signal": self.signal,
            "quantile_k": self.quantile_k,
            "periods": self.periods,
            "gross_mean_return": _round_opt(self.gross_mean_return),
            "net_mean_return": _round_opt(self.net_mean_return),
            "win_rate": _round_opt(self.win_rate),
            "sharpe": _round_opt(self.sharpe),
            "deflated": self.deflated.to_dict() if self.deflated else None,
            "path": self.path.to_dict() if self.path else None,
            "avg_turnover": _round_opt(self.avg_turnover),
            "has_significant_edge": self.has_significant_edge,
        }


def select_long_short(
    signal_by_symbol: dict[str, float | None], *, k: int
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Long the bottom-k (losers), short the top-k (winners) by signal."""

    valid = {
        symbol: value
        for symbol, value in signal_by_symbol.items()
        if value is not None and math.isfinite(value)
    }
    if len(valid) < 2 * k:
        return (), ()
    ordered = sorted(valid, key=lambda symbol: (valid[symbol], symbol))
    return tuple(ordered[:k]), tuple(ordered[-k:])


def _leg_mean(symbols: tuple[str, ...], forward_by_symbol: dict[str, float | None]) -> float | None:
    values = [
        value
        for symbol in symbols
        if (value := forward_by_symbol.get(symbol)) is not None
        and abs(value) <= MAX_ABS_PERIOD_RETURN
    ]
    return sum(values) / len(values) if values else None


def gross_period_return(
    long: tuple[str, ...],
    short: tuple[str, ...],
    forward_by_symbol: dict[str, float | None],
) -> float | None:
    long_return = _leg_mean(long, forward_by_symbol)
    short_return = _leg_mean(short, forward_by_symbol)
    if long_return is None or short_return is None:
        return None
    return long_return - short_return  # reversal: long losers, short winners


def one_way_turnover(previous: set[str], current: set[str]) -> float:
    if not current:
        return 0.0
    return len(current - previous) / len(current)


def run_xs_backtest(
    signal: str,
    gross_returns: list[float],
    turnovers: list[float],
    *,
    quantile_k: int,
    cost_bps: float,
    periods_per_year: int,
    trials: int,
) -> XSBacktestReport:
    round_trip = cost_bps / 10_000.0
    net = [gross - turnover * round_trip for gross, turnover in zip(gross_returns, turnovers, strict=True)]
    n = len(net)
    if n == 0:
        return XSBacktestReport(signal, quantile_k, 0, None, None, None, None, None, None, None)

    gross_mean = sum(gross_returns) / n
    net_mean = sum(net) / n
    win_rate = sum(1 for value in net if value > 0) / n
    sharpe = deflated = path = None
    if n >= 2:
        sharpe = sharpe_ratio(net, periods_per_year=periods_per_year)
        deflated = deflated_sharpe_ratio(
            raw_sharpe=sharpe,
            returns_count=n,
            trials=trials,
            periods_per_year=periods_per_year,
        )
        path = calculate_path_metrics(net)
    return XSBacktestReport(
        signal=signal,
        quantile_k=quantile_k,
        periods=n,
        gross_mean_return=gross_mean,
        net_mean_return=net_mean,
        win_rate=win_rate,
        sharpe=sharpe,
        deflated=deflated,
        path=path,
        avg_turnover=sum(turnovers) / len(turnovers) if turnovers else None,
    )


def _round_opt(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)
