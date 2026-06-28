from datetime import datetime, timedelta, timezone

import pytest

from app.services.backtest.replay import (
    _forward_returns,
    bars_from_rows,
    directional_outcome_label,
    replay_symbol_signals,
)
from app.services.signals.types import MarketBar

_BASE = datetime(2020, 1, 1, tzinfo=timezone.utc)


def test_directional_outcome_label_matches_hit_logic():
    assert directional_outcome_label("bullish", 0.02) == "hit"
    assert directional_outcome_label("bullish", -0.02) == "miss"
    assert directional_outcome_label("bearish", -0.02) == "hit"
    assert directional_outcome_label("bearish", 0.02) == "miss"
    assert directional_outcome_label("bullish", None) == "pending"
    assert directional_outcome_label(None, 0.02) == "pending"


def test_forward_returns_slice_and_bound():
    closes = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
    forward = _forward_returns(closes, 0)
    assert forward[1] == pytest.approx(0.01)
    assert forward[5] == pytest.approx(0.05)
    assert forward[20] is None  # not enough forward bars


def test_bars_from_rows_sorts_ascending():
    class _Row:
        def __init__(self, ts, close):
            self.timestamp = ts
            self.open = close
            self.high = close + 1
            self.low = close - 1
            self.close = close
            self.volume = 1000
            self.open_interest = None

    rows = [_Row(_BASE + timedelta(days=2), 102), _Row(_BASE, 100), _Row(_BASE + timedelta(days=1), 101)]
    bars = bars_from_rows(rows)
    assert [bar.close for bar in bars] == [100, 101, 102]


def _flat_then_jump_series(*, n_flat: int = 24, n_after: int = 6) -> list[MarketBar]:
    bars: list[MarketBar] = []
    for day in range(n_flat):
        bars.append(
            MarketBar(
                timestamp=_BASE + timedelta(days=day),
                open=100.0,
                high=100.5,
                low=99.5,
                close=100.0,
                volume=1000.0,
            )
        )
    # a sharp gap up with a volume spike -> price_gap (and a momentum cross)
    bars.append(
        MarketBar(
            timestamp=_BASE + timedelta(days=n_flat),
            open=100.0,
            high=106.5,
            low=100.0,
            close=106.0,
            volume=5000.0,
        )
    )
    for step in range(1, n_after + 1):
        close = 106.0 + step
        bars.append(
            MarketBar(
                timestamp=_BASE + timedelta(days=n_flat + step),
                open=close - 1,
                high=close + 0.5,
                low=close - 1.5,
                close=close,
                volume=1500.0,
            )
        )
    return bars


async def test_replay_emits_bullish_price_signal_on_a_jump():
    bars = _flat_then_jump_series()

    signals = await replay_symbol_signals("RB", bars)

    assert signals, "expected at least one replayed signal"
    bullish = [s for s in signals if s.direction == "bullish"]
    assert bullish, "the gap-up should produce a bullish directional signal"

    price_gaps = [s for s in signals if s.signal_type == "price_gap"]
    assert price_gaps
    gap = price_gaps[0]
    assert gap.direction == "bullish"
    # price kept rising after the gap, so the forward return is positive -> hit
    assert gap.forward_return_5d is not None and gap.forward_return_5d > 0
    assert gap.outcome == "hit"


async def test_replay_quiet_series_emits_nothing():
    flat = [
        MarketBar(
            timestamp=_BASE + timedelta(days=day),
            open=100.0,
            high=100.2,
            low=99.8,
            close=100.0,
            volume=1000.0,
        )
        for day in range(40)
    ]
    signals = await replay_symbol_signals("RB", flat)
    assert signals == []
