from types import SimpleNamespace

import pytest

from app.services.prediction.divergence import (
    LivePerformance,
    assess_divergence,
    demote_signal,
    live_performance_from_returns,
)
from app.services.prediction.production import bounded_weights, production_weights


def test_bounded_weights_scales_gross_to_cap():
    weights = {f"L{i}": 0.1 for i in range(10)} | {f"S{i}": -0.1 for i in range(10)}
    bounded = bounded_weights(weights, max_gross=1.0, max_per_symbol=0.15)
    # raw gross 2.0 -> scaled to 1.0 (each 0.1 -> 0.05)
    assert sum(abs(w) for w in bounded.values()) == pytest.approx(1.0)
    assert all(abs(w) == pytest.approx(0.05) for w in bounded.values())


def test_bounded_weights_caps_per_symbol():
    bounded = bounded_weights({"A": 0.3, "B": -0.3}, max_gross=1.0, max_per_symbol=0.15)
    assert bounded == {"A": 0.15, "B": -0.15}  # capped per-symbol, gross 0.3 < 1.0


def test_production_weights_zero_for_shadow_nonzero_for_authoritative():
    shadow = SimpleNamespace(decision_grade=False, target_weights={"A": 0.1, "B": -0.1})
    assert production_weights(shadow) == {}

    authoritative = SimpleNamespace(decision_grade=True, target_weights={"A": 0.3, "B": -0.3})
    assert production_weights(authoritative, max_per_symbol=0.15) == {"A": 0.15, "B": -0.15}


def test_live_performance_drawdown():
    perf = live_performance_from_returns([0.02, -0.01, 0.03])
    assert perf.periods == 3
    assert perf.mean_return == pytest.approx((0.02 - 0.01 + 0.03) / 3)
    assert perf.max_drawdown == pytest.approx(-0.01)


def test_assess_divergence_rules():
    # too few live periods -> never breach
    assert assess_divergence(LivePerformance(5, 0.0, -1.0, -0.5), min_live_periods=10) == (False, None)
    # enough periods + negative sharpe -> breach
    breached, reason = assess_divergence(LivePerformance(12, -0.01, -0.5, -0.02), min_live_periods=10)
    assert breached and "sharpe" in reason
    # drawdown breach
    breached, reason = assess_divergence(
        LivePerformance(12, 0.0, 0.5, -0.15), min_live_periods=10, max_drawdown=0.10
    )
    assert breached and "drawdown" in reason
    # healthy live track -> no breach
    assert assess_divergence(LivePerformance(12, 0.01, 0.8, -0.04), min_live_periods=10) == (False, None)


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.flushed = 0

    async def scalars(self, statement):
        return _Scalars(self._rows)

    async def flush(self):
        self.flushed += 1


async def test_demote_signal_flips_approved_review_to_demoted():
    review = SimpleNamespace(status="approved", proposed_change={"signal": "xs_reversal_mom120"})
    session = _FakeSession([review])

    demoted = await demote_signal(
        session, signal="xs_reversal_mom120", model_version="xs_reversal/1.0", reason="live broke"
    )

    assert demoted is True
    assert review.status == "demoted"  # -> is_signal_promoted now returns False (kill switch)
    assert review.proposed_change["demotion"]["reason"] == "live broke"


async def test_demote_signal_no_approved_review():
    session = _FakeSession([])
    demoted = await demote_signal(
        session, signal="x", model_version="v", reason="r"
    )
    assert demoted is False
