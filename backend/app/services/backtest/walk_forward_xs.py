"""Walk-forward / out-of-sample validation for the cross-sectional reversal strategy.

The full-sample backtest is significant, but the SIGNAL (reversal at mom_60/120)
was chosen after seeing the full-sample IC. Two checks close that gap:

* ``sub_period_breakdown`` — is the edge consistent across calendar sub-periods,
  or driven by one lucky stretch?
* ``walk_forward_oos`` — at each step, select the best signal using ONLY the
  trailing training window, then apply it to the next unseen test window. The
  concatenated test returns are a genuine out-of-sample track: if it is
  significant, the strategy + selection generalize (you could have traded it).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.services.backtest.multiple_testing import (
    DeflatedSharpeResult,
    deflated_sharpe_ratio,
    sharpe_ratio,
)

DatedReturns = list[tuple[datetime, float]]


@dataclass(frozen=True, slots=True)
class SubPeriod:
    label: str
    periods: int
    mean_return: float
    win_rate: float
    sharpe: float


@dataclass(frozen=True, slots=True)
class WalkForwardResult:
    oos_periods: int
    oos_mean_return: float
    oos_win_rate: float
    oos_sharpe: float
    oos_deflated: DeflatedSharpeResult | None
    selections: tuple[tuple[str, str], ...]  # (test_window_start_iso, selected_signal)

    @property
    def has_significant_edge(self) -> bool:
        return self.oos_deflated is not None and self.oos_deflated.passed_gate


def _sharpe(returns: list[float], periods_per_year: int) -> float:
    return sharpe_ratio(returns, periods_per_year=periods_per_year) if len(returns) >= 2 else 0.0


def sub_period_breakdown(
    dated_returns: DatedReturns, *, n_blocks: int, periods_per_year: int
) -> list[SubPeriod]:
    n = len(dated_returns)
    if n == 0:
        return []
    size = max(1, n // n_blocks)
    blocks: list[SubPeriod] = []
    for block in range(n_blocks):
        start = block * size
        chunk = dated_returns[start:] if block == n_blocks - 1 else dated_returns[start : start + size]
        if not chunk:
            continue
        returns = [value for _, value in chunk]
        wins = sum(1 for value in returns if value > 0) / len(returns)
        blocks.append(
            SubPeriod(
                label=f"{chunk[0][0].date()}..{chunk[-1][0].date()}",
                periods=len(returns),
                mean_return=sum(returns) / len(returns),
                win_rate=wins,
                sharpe=_sharpe(returns, periods_per_year),
            )
        )
    return blocks


def walk_forward_oos(
    returns_by_signal: dict[str, DatedReturns],
    *,
    train: int,
    test: int,
    periods_per_year: int,
) -> WalkForwardResult:
    signals = sorted(returns_by_signal)
    if not signals:
        return WalkForwardResult(0, 0.0, 0.0, 0.0, None, ())
    timeline = [day for day, _ in returns_by_signal[signals[0]]]
    by_signal = {signal: dict(returns_by_signal[signal]) for signal in signals}

    oos: DatedReturns = []
    selections: list[tuple[str, str]] = []
    cursor = train
    while cursor + test <= len(timeline):
        train_days = timeline[cursor - train : cursor]
        test_days = timeline[cursor : cursor + test]

        best_signal = signals[0]
        best_sharpe = float("-inf")
        for signal in signals:
            train_returns = [by_signal[signal][day] for day in train_days if day in by_signal[signal]]
            candidate = _sharpe(train_returns, periods_per_year)
            if candidate > best_sharpe:
                best_sharpe, best_signal = candidate, signal

        for day in test_days:
            if day in by_signal[best_signal]:
                oos.append((day, by_signal[best_signal][day]))
        selections.append((test_days[0].date().isoformat(), best_signal))
        cursor += test

    returns = [value for _, value in oos]
    n = len(returns)
    if n == 0:
        return WalkForwardResult(0, 0.0, 0.0, 0.0, None, tuple(selections))
    mean = sum(returns) / n
    win_rate = sum(1 for value in returns if value > 0) / n
    sharpe = _sharpe(returns, periods_per_year)
    deflated = (
        deflated_sharpe_ratio(
            raw_sharpe=sharpe, returns_count=n, trials=1, periods_per_year=periods_per_year
        )
        if n >= 2
        else None
    )
    return WalkForwardResult(n, mean, win_rate, sharpe, deflated, tuple(selections))
