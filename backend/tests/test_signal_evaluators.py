from datetime import datetime, timedelta, timezone

import pytest

from app.services.signals.detector import SignalDetector
from app.services.signals.evaluators.basis_shift import BasisShiftEvaluator
from app.services.signals.evaluators.event_driven import EventDrivenEvaluator
from app.services.signals.evaluators.inventory_shock import InventoryShockEvaluator
from app.services.signals.evaluators.momentum import MomentumEvaluator
from app.services.signals.evaluators.news_event import NewsEventEvaluator
from app.services.signals.evaluators.price_gap import PriceGapEvaluator
from app.services.signals.evaluators.regime_shift import RegimeShiftEvaluator
from app.services.signals.evaluators.spread_anomaly import SpreadAnomalyEvaluator
from app.services.signals.types import (
    IndustryPoint,
    MarketBar,
    NewsEventPoint,
    SpreadStatistics,
    TriggerContext,
)


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

    assert [result.signal_type for result in results] == ["spread_anomaly", "basis_shift"]


@pytest.mark.asyncio
async def test_signal_detector_degrades_spread_signals_in_roll_window() -> None:
    context = TriggerContext(
        symbol1="RB",
        symbol2="HC",
        category="ferrous",
        timestamp=datetime.now(timezone.utc),
        in_roll_window=True,
        spread_stats=SpreadStatistics(
            adf_p_value=0.03,
            half_life=12,
            spread_mean=10,
            spread_std_dev=2,
            current_z_score=2.8,
        ),
    )

    results = await SignalDetector().detect(context)

    assert results == []


@pytest.mark.asyncio
async def test_basis_shift_triggers_on_basis_deviation() -> None:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    market_data = [
        MarketBar(
            timestamp=start + timedelta(days=idx),
            open=100 + idx,
            high=101 + idx,
            low=99 + idx,
            close=100 + idx,
            volume=100 + idx * 30,
        )
        for idx in range(5)
    ]
    context = TriggerContext(
        symbol1="RB",
        symbol2="HC",
        category="ferrous",
        timestamp=datetime.now(timezone.utc),
        market_data=market_data,
        spread_stats=SpreadStatistics(
            adf_p_value=0.04,
            half_life=10,
            spread_mean=10,
            spread_std_dev=2,
            current_z_score=2.4,
        ),
    )

    result = await BasisShiftEvaluator().evaluate(context)

    assert result is not None
    assert result.signal_type == "basis_shift"


@pytest.mark.asyncio
async def test_regime_shift_triggers_on_volatility_jump() -> None:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    closes = [100 + idx * 0.1 for idx in range(25)] + [103, 96, 108, 92, 115, 88, 121]
    market_data = [
        MarketBar(
            timestamp=start + timedelta(days=idx),
            open=close,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=100,
        )
        for idx, close in enumerate(closes)
    ]

    result = await RegimeShiftEvaluator().evaluate(
        TriggerContext(
            symbol1="RB",
            category="ferrous",
            timestamp=datetime.now(timezone.utc),
            market_data=market_data,
        )
    )

    assert result is not None
    assert result.signal_type == "regime_shift"


@pytest.mark.asyncio
async def test_inventory_shock_uses_inventory_and_volatility() -> None:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    market_data = [
        MarketBar(
            timestamp=start + timedelta(days=idx),
            open=100,
            high=101 + idx,
            low=99 - idx,
            close=100,
            volume=100,
        )
        for idx in range(15)
    ]
    inventory = [
        IndustryPoint(value=value, timestamp=start + timedelta(days=idx))
        for idx, value in enumerate([100, 101, 99, 100, 98, 130, 132, 135])
    ]

    result = await InventoryShockEvaluator().evaluate(
        TriggerContext(
            symbol1="RB",
            category="ferrous",
            timestamp=datetime.now(timezone.utc),
            market_data=market_data,
            inventory=inventory,
        )
    )

    assert result is not None
    assert result.signal_type == "inventory_shock"


@pytest.mark.asyncio
async def test_event_driven_triggers_on_gap_and_volume_spike() -> None:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    closes = [100.0, 100.2, 99.8, 100.1, 108.0]
    market_data = [
        MarketBar(
            timestamp=start + timedelta(days=idx),
            open=close,
            high=close + 0.3,
            low=close - 0.3,
            close=close,
            volume=500 if idx == len(closes) - 1 else 100,
        )
        for idx, close in enumerate(closes)
    ]

    result = await EventDrivenEvaluator().evaluate(
        TriggerContext(
            symbol1="RB",
            category="ferrous",
            timestamp=datetime.now(timezone.utc),
            market_data=market_data,
        )
    )

    assert result is not None
    assert result.signal_type == "event_driven"


@pytest.mark.asyncio
async def test_price_gap_triggers_with_new_signal_type() -> None:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    closes = [100.0, 100.2, 99.8, 100.1, 108.0]
    market_data = [
        MarketBar(
            timestamp=start + timedelta(days=idx),
            open=close,
            high=close + 0.3,
            low=close - 0.3,
            close=close,
            volume=500 if idx == len(closes) - 1 else 100,
        )
        for idx, close in enumerate(closes)
    ]

    result = await PriceGapEvaluator().evaluate(
        TriggerContext(
            symbol1="RB",
            category="ferrous",
            timestamp=datetime.now(timezone.utc),
            market_data=market_data,
        )
    )

    assert result is not None
    assert result.signal_type == "price_gap"


@pytest.mark.asyncio
async def test_news_event_triggers_for_cross_verified_severe_event() -> None:
    event = NewsEventPoint(
        id="evt-1",
        source="cailianshe",
        title="OPEC+ extends production cuts",
        summary="OPEC+ extends production cuts, bullish for crude oil.",
        published_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        event_type="supply",
        affected_symbols=["SC"],
        direction="bullish",
        severity=5,
        time_horizon="medium",
        confidence=0.82,
        source_count=2,
        verification_status="cross_verified",
    )

    result = await NewsEventEvaluator().evaluate(
        TriggerContext(
            symbol1="SC",
            category="energy",
            timestamp=datetime.now(timezone.utc),
            news_events=[event],
        )
    )

    assert result is not None
    assert result.signal_type == "news_event"
    assert result.severity == "critical"
    assert result.related_assets == ["SC"]


@pytest.mark.asyncio
async def test_news_event_requires_cross_source_or_manual_confirmation() -> None:
    event = NewsEventPoint(
        id="evt-2",
        source="exchange_announcements",
        title="Exchange risk notice",
        summary="Single source policy event.",
        published_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        event_type="policy",
        affected_symbols=["I"],
        direction="mixed",
        severity=4,
        time_horizon="immediate",
        confidence=0.7,
        source_count=1,
        verification_status="single_source",
        requires_manual_confirmation=True,
    )

    result = await NewsEventEvaluator().evaluate(
        TriggerContext(
            symbol1="I",
            category="ferrous",
            timestamp=datetime.now(timezone.utc),
            news_events=[event],
        )
    )

    assert result is None


def test_all_evaluators_expose_outcome_evaluation() -> None:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    market_data = [
        MarketBar(
            timestamp=start + timedelta(days=idx),
            open=100 + idx,
            high=101 + idx,
            low=99 + idx,
            close=100 + idx,
            volume=100,
        )
        for idx in range(25)
    ]
    signal = {
        "title": "RB bullish momentum signal",
        "summary": "RB generated a bullish signal.",
        "risk_items": ["Bullish moving-average crossover."],
        "related_assets": ["RB"],
        "spread_info": {
            "leg1": "RB",
            "leg2": "HC",
            "current_spread": 106,
            "historical_mean": 100,
            "sigma1_upper": 102,
            "sigma1_lower": 98,
            "z_score": 3,
            "half_life": 10,
            "adf_p_value": 0.03,
        },
    }

    evaluators = [
        SpreadAnomalyEvaluator(),
        BasisShiftEvaluator(),
        MomentumEvaluator(),
        RegimeShiftEvaluator(),
        InventoryShockEvaluator(),
        EventDrivenEvaluator(),
        PriceGapEvaluator(),
        NewsEventEvaluator(),
    ]

    outcomes = [
        evaluator.evaluate_outcome(signal, market_data, horizon_days=20).outcome
        for evaluator in evaluators
    ]

    assert outcomes == ["hit", "hit", "hit", "miss", "miss", "hit", "hit", "hit"]
