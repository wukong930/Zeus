import math
from datetime import datetime, timedelta, timezone

import pytest

from app.services.prediction.cross_sectional import (
    build_forecast,
    feature_hash,
    generate_cross_sectional_forecast,
    reversal_weights,
    trailing_momentum,
)
from app.services.signals.types import MarketBar

_BASE = datetime(2020, 1, 1, tzinfo=timezone.utc)


def test_trailing_momentum_log_return_over_lookback():
    closes = [100.0] * 120 + [110.0]
    assert trailing_momentum(closes, 120) == pytest.approx(math.log(110 / 100))
    assert trailing_momentum([100.0, 101.0], 120) is None  # not enough history


def test_reversal_weights_long_losers_short_winners_dollar_neutral():
    momentum = {"A": -0.3, "B": -0.2, "C": -0.1, "D": 0.1, "E": 0.2, "F": 0.3}
    weights = reversal_weights(momentum, k=2)
    assert weights == {"A": 0.5, "B": 0.5, "E": -0.5, "F": -0.5}
    assert sum(weights.values()) == pytest.approx(0.0)  # dollar-neutral
    # too few symbols -> no position
    assert reversal_weights({"A": -0.1, "B": 0.1}, k=2) == {}


def test_feature_hash_is_deterministic_and_input_sensitive():
    momentum = {"A": -0.3, "B": 0.3}
    h1 = feature_hash(_BASE, "xs_reversal_mom120", momentum)
    h2 = feature_hash(_BASE, "xs_reversal_mom120", dict(momentum))
    assert h1 == h2  # reproducible
    assert feature_hash(_BASE, "xs_reversal_mom120", {"A": -0.3, "B": 0.31}) != h1


def test_build_forecast_shape():
    momentum = {"A": -0.3, "B": -0.2, "C": -0.1, "D": 0.1, "E": 0.2, "F": 0.3}
    forecast = build_forecast(_BASE, momentum, lookback=120, k=2)
    assert forecast.signal == "xs_reversal_mom120"
    assert forecast.model_version == "xs_reversal/1.0"
    assert forecast.universe_size == 6
    assert forecast.target_weights == {"A": 0.5, "B": 0.5, "E": -0.5, "F": -0.5}


class _FakeSession:
    def __init__(self):
        self.added = []
        self.flushed = 0

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        self.flushed += 1


async def test_generate_forecast_is_shadow_and_persists(monkeypatch):
    momenta = {"A": -0.3, "B": -0.2, "C": -0.1, "D": 0.1, "E": 0.2, "F": 0.3}
    as_of = _BASE + timedelta(days=10)

    async def fake_load_main_series(session, symbol, *, as_of=None, limit=20000):
        m = momenta[symbol]
        closes = [100.0, 100.0, 100.0 * math.exp(m)]
        return [
            MarketBar(
                timestamp=_BASE + timedelta(days=i),
                open=c,
                high=c,
                low=c,
                close=c,
                volume=0.0,
            )
            for i, c in enumerate(closes)
        ]

    monkeypatch.setattr(
        "app.services.prediction.cross_sectional.load_main_series", fake_load_main_series
    )
    session = _FakeSession()

    row = await generate_cross_sectional_forecast(
        session,  # type: ignore[arg-type]
        as_of=as_of,
        lookback=2,
        k=2,
        symbols=list(momenta),
    )

    assert row.signal == "xs_reversal_mom2"
    assert row.decision_grade is False  # advisory / shadow, never authoritative here
    assert row.universe_size == 6
    assert row.target_weights == {"A": 0.5, "B": 0.5, "E": -0.5, "F": -0.5}
    assert len(row.feature_hash) == 64
    assert session.added == [row] and session.flushed == 1
