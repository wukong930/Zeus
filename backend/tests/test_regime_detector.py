from app.services.calibration.regime_detector import (
    REGIME_RANGE_HIGH_VOL,
    REGIME_RANGE_LOW_VOL,
    REGIME_TREND_DOWN_LOW_VOL,
    REGIME_TREND_UP_LOW_VOL,
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
    assert classify_regime(adx=15, atr_percentile=80, trend_direction="flat") == REGIME_RANGE_HIGH_VOL
    assert classify_regime(adx=18, atr_percentile=30, trend_direction="flat") == REGIME_RANGE_LOW_VOL


def test_percentile_rank_returns_percentage() -> None:
    assert percentile_rank([1, 2, 3, 4], 3) == 75
