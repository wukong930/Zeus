from datetime import date, datetime, timezone

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
