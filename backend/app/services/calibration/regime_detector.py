from dataclasses import dataclass
from statistics import mean

from app.services.signals.types import MarketBar

REGIME_TREND_UP_LOW_VOL = "trend_up_low_vol"
REGIME_TREND_DOWN_LOW_VOL = "trend_down_low_vol"
REGIME_RANGE_HIGH_VOL = "range_high_vol"
REGIME_RANGE_LOW_VOL = "range_low_vol"


@dataclass(frozen=True)
class RegimeDetection:
    regime: str
    adx: float
    atr_percentile: float
    trend_direction: str
    sample_size: int


def classify_regime(*, adx: float, atr_percentile: float, trend_direction: str) -> str:
    if adx > 25 and atr_percentile < 50 and trend_direction == "up":
        return REGIME_TREND_UP_LOW_VOL
    if adx > 25 and atr_percentile < 50 and trend_direction == "down":
        return REGIME_TREND_DOWN_LOW_VOL
    if adx < 20 and atr_percentile > 70:
        return REGIME_RANGE_HIGH_VOL
    return REGIME_RANGE_LOW_VOL


def detect_regime(bars: list[MarketBar], *, period: int = 14) -> RegimeDetection:
    if len(bars) < period + 2:
        return RegimeDetection(
            regime=REGIME_RANGE_LOW_VOL,
            adx=0,
            atr_percentile=0,
            trend_direction="flat",
            sample_size=len(bars),
        )

    ordered = sorted(bars, key=lambda bar: bar.timestamp)
    true_ranges = _true_ranges(ordered)
    atr_values = _rolling_mean(true_ranges, period)
    latest_atr = atr_values[-1]
    atr_percentile = percentile_rank(atr_values, latest_atr)
    adx = calculate_adx(ordered, period=period)
    trend_direction = _trend_direction(ordered)
    return RegimeDetection(
        regime=classify_regime(
            adx=adx,
            atr_percentile=atr_percentile,
            trend_direction=trend_direction,
        ),
        adx=adx,
        atr_percentile=atr_percentile,
        trend_direction=trend_direction,
        sample_size=len(ordered),
    )


def calculate_adx(bars: list[MarketBar], *, period: int = 14) -> float:
    if len(bars) < period + 2:
        return 0.0

    plus_dm: list[float] = []
    minus_dm: list[float] = []
    true_ranges = _true_ranges(bars)
    for previous, current in zip(bars, bars[1:], strict=False):
        up_move = current.high - previous.high
        down_move = previous.low - current.low
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)

    dx_values: list[float] = []
    for idx in range(period - 1, len(true_ranges)):
        tr_sum = sum(true_ranges[idx - period + 1 : idx + 1])
        if tr_sum <= 0:
            continue
        plus_di = 100 * sum(plus_dm[idx - period + 1 : idx + 1]) / tr_sum
        minus_di = 100 * sum(minus_dm[idx - period + 1 : idx + 1]) / tr_sum
        denominator = plus_di + minus_di
        dx_values.append(0.0 if denominator <= 0 else 100 * abs(plus_di - minus_di) / denominator)

    if not dx_values:
        return 0.0
    return mean(dx_values[-period:])


def percentile_rank(values: list[float], value: float) -> float:
    if not values:
        return 0.0
    below_or_equal = sum(1 for item in values if item <= value)
    return below_or_equal / len(values) * 100


def _true_ranges(bars: list[MarketBar]) -> list[float]:
    ranges: list[float] = []
    for idx, bar in enumerate(bars):
        if idx == 0:
            ranges.append(bar.high - bar.low)
            continue
        previous_close = bars[idx - 1].close
        ranges.append(
            max(
                bar.high - bar.low,
                abs(bar.high - previous_close),
                abs(bar.low - previous_close),
            )
        )
    return ranges


def _rolling_mean(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return values
    return [mean(values[idx - period + 1 : idx + 1]) for idx in range(period - 1, len(values))]


def _trend_direction(bars: list[MarketBar]) -> str:
    first = bars[0].close
    last = bars[-1].close
    if last > first:
        return "up"
    if last < first:
        return "down"
    return "flat"
