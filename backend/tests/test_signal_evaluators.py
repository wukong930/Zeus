from datetime import datetime, timedelta, timezone

import pytest

from app.services.signals.detector import SignalDetector
from app.services.signals.evaluators.momentum import MomentumEvaluator
from app.services.signals.evaluators.spread_anomaly import SpreadAnomalyEvaluator
from app.services.signals.types import MarketBar, SpreadStatistics, TriggerContext


@pytest.mark.asyncio
async def test_spread_anomaly_triggers_on_large_z_score() -> None:
    context = TriggerContext(
        symbol1="RB",
        symbol2="HC",
        category="ferrous",
        timestamp=datetime.now(timezone.utc),
        spread_stats=SpreadStatistics(
            adf_p_value=0.03,
            half_life=12,
            spread_mean=10,
            spread_std_dev=2,
            current_z_score=2.8,
        ),
    )

    result = await SpreadAnomalyEvaluator().evaluate(context)

    assert result is not None
    assert result.severity == "high"
    assert result.spread_info is not None
    assert result.spread_info.current_spread == 15.6


@pytest.mark.asyncio
async def test_momentum_triggers_on_ma_cross_with_volume_confirmation() -> None:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    closes = [100.0] * 16 + [95.0] * 4 + [130.0]
    market_data = [
        MarketBar(
            timestamp=start + timedelta(days=idx),
            open=close,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=200 if idx == len(closes) - 1 else 100,
        )
        for idx, close in enumerate(closes)
    ]
    context = TriggerContext(
        symbol1="RB",
        category="ferrous",
        timestamp=datetime.now(timezone.utc),
        market_data=market_data,
    )

    result = await MomentumEvaluator().evaluate(context)

    assert result is not None
    assert result.severity == "high"
    assert result.signal_type == "momentum"


@pytest.mark.asyncio
async def test_signal_detector_runs_evaluators_in_parallel() -> None:
    context = TriggerContext(
        symbol1="RB",
        symbol2="HC",
        category="ferrous",
        timestamp=datetime.now(timezone.utc),
        spread_stats=SpreadStatistics(
            adf_p_value=0.03,
            half_life=12,
            spread_mean=10,
            spread_std_dev=2,
            current_z_score=2.8,
        ),
    )

    results = await SignalDetector().detect(context)

    assert [result.signal_type for result in results] == ["spread_anomaly"]
