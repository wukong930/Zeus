from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.prediction.shadow import (
    _holding_return,
    score_due_forecasts,
    weighted_realized_return,
)
from app.services.signals.types import MarketBar

_D = datetime(2020, 6, 1, tzinfo=timezone.utc)


def test_weighted_realized_return_sums_and_guards():
    weights = {"A": 0.5, "B": -0.5}
    assert weighted_realized_return(weights, {"A": 0.10, "B": -0.05}) == pytest.approx(0.075)
    # an unpriced leg -> None (holding period not elapsed)
    assert weighted_realized_return(weights, {"A": 0.10, "B": None}) is None
    # a roll artifact leg is neutralized, not allowed to dominate
    assert weighted_realized_return({"A": 1.0}, {"A": 3.0}) == pytest.approx(0.0)


def test_holding_return_uses_entry_at_as_of_and_exit_at_horizon():
    dates = [_D + timedelta(days=i) for i in range(3)]
    closes = [100.0, 105.0, 110.0]
    assert _holding_return(dates, closes, _D, 2) == pytest.approx(0.10)
    # horizon not elapsed in the data -> None
    assert _holding_return(dates, closes, _D, 5) is None


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.flushed = 0

    async def scalars(self, statement):
        return _Scalars(self._rows)

    async def flush(self):
        self.flushed += 1


async def test_score_due_forecasts_fills_realized_return(monkeypatch):
    forecast = SimpleNamespace(
        target_weights={"A": 0.5, "B": -0.5},
        horizon_days=2,
        as_of=_D,
        realized_return=None,
        resolved_at=None,
    )
    series = {"A": [100.0, 105.0, 110.0], "B": [100.0, 98.0, 95.0]}

    async def fake_load_main_series(session, symbol, *, as_of=None, limit=20000):
        return [
            MarketBar(
                timestamp=_D + timedelta(days=i),
                open=c,
                high=c,
                low=c,
                close=c,
                volume=0.0,
            )
            for i, c in enumerate(series[symbol])
        ]

    monkeypatch.setattr("app.services.prediction.shadow.load_main_series", fake_load_main_series)
    session = _FakeSession([forecast])

    result = await score_due_forecasts(session, now=_D + timedelta(days=30))

    # realized = 0.5*(+0.10) + (-0.5)*(-0.05) = 0.075
    assert forecast.realized_return == pytest.approx(0.075)
    assert forecast.resolved_at == _D + timedelta(days=30)
    assert result.resolved == 1 and result.pending == 0
