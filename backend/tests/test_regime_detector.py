from datetime import date, datetime, timedelta, timezone

from app.models.market_data import MarketData
from app.services.calibration.regime_batch import (
    SymbolRegimeDetection,
    aggregate_category_regime,
    market_row_to_bar,
)
from app.services.calibration.regime_detector import (
    REGIME_RANGE_HIGH_VOL,
    REGIME_RANGE_LOW_VOL,
    REGIME_TREND_DOWN_LOW_VOL,
    REGIME_TREND_UP_LOW_VOL,
    RegimeDetection,
    classify_regime,
    percentile_rank,
)
from app.services.calibration.regime_hmm_baseline import (
    describe_regime_switches,
    market_bars_to_hmm_features,
    run_hmm_regime_baseline,
    sequence_stability,
)
from app.services.signals.types import MarketBar


def test_classify_regime_uses_adx_atr_and_direction() -> None:
    assert (
        classify_regime(adx=30, atr_percentile=40, trend_direction="up")
        == REGIME_TREND_UP_LOW_VOL
    )
    assert (
        classify_regime(adx=30, atr_percentile=40, trend_direction="down")
        == REGIME_TREND_DOWN_LOW_VOL
    )
    assert (
        classify_regime(adx=15, atr_percentile=80, trend_direction="flat")
        == REGIME_RANGE_HIGH_VOL
    )
    assert (
        classify_regime(adx=18, atr_percentile=30, trend_direction="flat")
        == REGIME_RANGE_LOW_VOL
    )


def test_percentile_rank_returns_percentage() -> None:
    assert percentile_rank([1, 2, 3, 4], 3) == 75


def test_aggregate_category_regime_uses_weighted_symbol_vote() -> None:
    aggregate = aggregate_category_regime(
        category="ferrous",
        as_of_date=date(2026, 5, 3),
        detections=[
            SymbolRegimeDetection(
                symbol="RB2601",
                detection=RegimeDetection(
                    regime=REGIME_TREND_UP_LOW_VOL,
                    adx=30,
                    atr_percentile=40,
                    trend_direction="up",
                    sample_size=80,
                ),
            ),
            SymbolRegimeDetection(
                symbol="HC2601",
                detection=RegimeDetection(
                    regime=REGIME_RANGE_LOW_VOL,
                    adx=10,
                    atr_percentile=20,
                    trend_direction="flat",
                    sample_size=20,
                ),
            ),
        ],
    )

    assert aggregate is not None
    assert aggregate.regime == REGIME_TREND_UP_LOW_VOL
    assert aggregate.trend_direction == "up"
    assert aggregate.adx == 26
    assert aggregate.sample_size == 100
    assert aggregate.symbol_count == 2


def test_market_row_to_bar_preserves_ohlcv_fields() -> None:
    timestamp = datetime(2026, 5, 3, tzinfo=timezone.utc)
    row = MarketData(
        market="CN",
        exchange="SHFE",
        commodity="rebar",
        symbol="RB2601",
        contract_month="2601",
        timestamp=timestamp,
        open=3500,
        high=3560,
        low=3480,
        close=3520,
        volume=1000,
        open_interest=500,
    )

    bar = market_row_to_bar(row)

    assert bar.timestamp == timestamp
    assert bar.open == 3500
    assert bar.high == 3560
    assert bar.low == 3480
    assert bar.close == 3520
    assert bar.volume == 1000
    assert bar.open_interest == 500


def test_market_bars_to_hmm_features_extracts_returns_ranges_and_volume_changes() -> None:
    bars = [
        MarketBar(
            timestamp=datetime(2026, 5, 1, tzinfo=timezone.utc),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1000,
        ),
        MarketBar(
            timestamp=datetime(2026, 5, 2, tzinfo=timezone.utc),
            open=100,
            high=103,
            low=99,
            close=102,
            volume=1100,
        ),
        MarketBar(
            timestamp=datetime(2026, 5, 3, tzinfo=timezone.utc),
            open=102,
            high=104,
            low=100,
            close=101,
            volume=990,
        ),
    ]

    features = market_bars_to_hmm_features(bars)

    assert len(features) == 2
    assert features[0].timestamp == "2026-05-02T00:00:00+00:00"
    assert features[0].return_pct == 2.0
    assert features[0].range_pct == 3.921569
    assert features[0].volume_change_pct == 10.0
    assert features[1].return_pct == -0.980392
    assert features[1].volume_change_pct == -10.0


def test_hmm_baseline_reports_insufficient_data_without_side_effects() -> None:
    report = run_hmm_regime_baseline(_synthetic_market_bars(8), min_features=30)

    assert report.status == "insufficient_data"
    assert report.sample_size == 8
    assert report.feature_count == 7
    assert report.latest_hmm_regime is None
    assert report.latest_rule_regime == REGIME_RANGE_LOW_VOL
    assert report.state_summaries == []
    assert report.observations == []


def test_hmm_baseline_completes_as_research_only_comparison() -> None:
    report = run_hmm_regime_baseline(
        _synthetic_market_bars(90),
        min_features=25,
        iterations=4,
        observation_tail=25,
    )
    known_regimes = {
        REGIME_TREND_UP_LOW_VOL,
        REGIME_TREND_DOWN_LOW_VOL,
        REGIME_RANGE_HIGH_VOL,
        REGIME_RANGE_LOW_VOL,
    }

    assert report.status == "completed"
    assert report.feature_count == 89
    assert report.latest_hmm_regime in known_regimes
    assert report.latest_rule_regime in known_regimes
    assert report.agreement_rate is not None
    assert 0 <= report.agreement_rate <= 1
    assert len(report.state_summaries) == report.states
    assert len(report.observations) == 25
    assert "not used by production" in report.note
    assert report.to_dict()["status"] == "completed"


def test_hmm_baseline_sequence_helpers_describe_switching_behavior() -> None:
    report = run_hmm_regime_baseline(_synthetic_market_bars(70), min_features=25, iterations=3)

    assert describe_regime_switches(report.observations) >= 0
    assert sequence_stability(["trend", "trend", "range", "range"]) == 0.6667
    assert sequence_stability(["trend"]) == 1.0


def _synthetic_market_bars(count: int) -> list[MarketBar]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars: list[MarketBar] = []
    previous_close = 100.0
    for idx in range(count):
        if idx < count // 2:
            close = 100 + idx * 0.22
            range_width = 0.8
            volume = 1000 + idx * 4
        else:
            close = 100 + count * 0.11 + ((-1) ** idx) * (1.2 + (idx % 5) * 0.25)
            range_width = 3.0
            volume = 1200 + (idx % 7) * 80
        bars.append(
            MarketBar(
                timestamp=base + timedelta(days=idx),
                open=previous_close,
                high=close + range_width,
                low=max(close - range_width, 1),
                close=close,
                volume=volume,
                open_interest=10000 + idx * 10,
            )
        )
        previous_close = close
    return bars
