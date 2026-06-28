"""Ratio back-adjustment of a futures continuous series from per-contract data.

The main-continuous (futures_main_sina) is NOT back-adjusted: it jumps at
contract rolls, biasing returns and spreads (the +341% spread artifacts).
Given per-contract daily closes + open interest, build a roll-free continuous
series: each day take the dominant contract (max open interest) and chain that
contract's OWN daily return — never the spurious old->new gap. The resulting
return series has no roll jumps; levels are rebased to an arbitrary start.

``raw_continuous_closes`` returns the same dominant-contract stitch WITHOUT
adjustment (roll gaps intact), so a backtest can compare adjusted vs raw on the
identical contract data and isolate the roll effect.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class ContractBar:
    contract: str  # e.g. "RB2405"
    day: date
    close: float
    open_interest: float


def _by_day(bars: list[ContractBar]) -> dict[date, dict[str, tuple[float, float]]]:
    grouped: dict[date, dict[str, tuple[float, float]]] = defaultdict(dict)
    for bar in bars:
        if bar.close > 0:
            grouped[bar.day][bar.contract] = (bar.close, bar.open_interest)
    return grouped


def _dominant(contracts: dict[str, tuple[float, float]]) -> str:
    # max open interest, deterministic tiebreak on contract code
    return max(contracts, key=lambda code: (contracts[code][1], code))


def raw_continuous_closes(bars: list[ContractBar]) -> list[tuple[date, float]]:
    """Dominant-contract close each day, WITHOUT roll adjustment (gaps intact)."""

    grouped = _by_day(bars)
    out: list[tuple[date, float]] = []
    for day in sorted(grouped):
        contracts = grouped[day]
        out.append((day, contracts[_dominant(contracts)][0]))
    return out


def back_adjusted_closes(
    bars: list[ContractBar], *, base: float = 100.0
) -> list[tuple[date, float]]:
    """Roll-free continuous: chain each day's dominant contract's own return."""

    grouped = _by_day(bars)
    days = sorted(grouped)
    out: list[tuple[date, float]] = []
    level = base
    prev_day: date | None = None
    for day in days:
        contracts = grouped[day]
        if prev_day is None:
            out.append((day, level))
            prev_day = day
            continue

        previous = grouped[prev_day]
        dominant = _dominant(contracts)
        # Today's dominant contract's own return (no roll gap) when it traded
        # yesterday; otherwise fall back to yesterday's dominant return.
        if dominant in previous and previous[dominant][0] > 0:
            ret = contracts[dominant][0] / previous[dominant][0]
        else:
            prev_dominant = _dominant(previous)
            if prev_dominant in contracts and previous[prev_dominant][0] > 0:
                ret = contracts[prev_dominant][0] / previous[prev_dominant][0]
            else:
                ret = 1.0
        level *= ret
        out.append((day, level))
        prev_day = day
    return out
