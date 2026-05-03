from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Literal

ContractTier = Literal["main", "second", "third"]
VolatilityBucket = Literal["low", "medium", "high"]
LiquidityBucket = Literal["lt_1pct_adv", "pct_1_to_5_adv", "gte_5pct_adv"]
TimeOfDayBucket = Literal["main_session", "open_15m", "close_15m", "night"]

BASE_SLIPPAGE_BPS_BY_TIER: dict[str, float] = {"main": 1.0, "second": 2.5, "third": 8.0}
VOL_MULTIPLIERS: dict[VolatilityBucket, float] = {"low": 0.7, "medium": 1.0, "high": 1.8}
LIQUIDITY_MULTIPLIERS: dict[LiquidityBucket, float] = {
    "lt_1pct_adv": 1.0,
    "pct_1_to_5_adv": 1.4,
    "gte_5pct_adv": 2.5,
}
TOD_MULTIPLIERS: dict[TimeOfDayBucket, float] = {
    "main_session": 1.0,
    "open_15m": 1.5,
    "close_15m": 1.4,
    "night": 1.2,
}


@dataclass(frozen=True, slots=True)
class SlippageEstimate:
    executable: bool
    slippage_bps: float | None
    contract_tier: str
    volatility_bucket: VolatilityBucket
    liquidity_bucket: LiquidityBucket
    time_of_day_bucket: TimeOfDayBucket
    delivery_multiplier_applied: bool = False
    recommended_contract_shift: bool = False
    reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "executable": self.executable,
            "slippage_bps": None if self.slippage_bps is None else round(self.slippage_bps, 4),
            "contract_tier": self.contract_tier,
            "volatility_bucket": self.volatility_bucket,
            "liquidity_bucket": self.liquidity_bucket,
            "time_of_day_bucket": self.time_of_day_bucket,
            "delivery_multiplier_applied": self.delivery_multiplier_applied,
            "recommended_contract_shift": self.recommended_contract_shift,
            "reason": self.reason,
        }


def calculate_slippage(
    *,
    symbol: str,
    contract_tier: ContractTier,
    atr_percentile: float,
    order_size: float,
    average_daily_volume: float,
    timestamp: datetime,
    days_to_delivery: int | None = None,
    limit_locked: bool = False,
    posted_at_limit: bool = False,
    base_slippage_bps: float | None = None,
) -> SlippageEstimate:
    vol_bucket = volatility_bucket(atr_percentile)
    liquidity_bucket_value = liquidity_bucket(order_size, average_daily_volume)
    tod_bucket = time_of_day_bucket(timestamp)
    if limit_locked and not posted_at_limit:
        return SlippageEstimate(
            executable=False,
            slippage_bps=None,
            contract_tier=contract_tier,
            volatility_bucket=vol_bucket,
            liquidity_bucket=liquidity_bucket_value,
            time_of_day_bucket=tod_bucket,
            reason=f"{symbol} limit-locked and no resting order is available.",
        )

    base = base_slippage_bps or BASE_SLIPPAGE_BPS_BY_TIER[contract_tier]
    delivery_multiplier = 3.0 if days_to_delivery is not None and days_to_delivery < 15 else 1.0
    slippage_bps = (
        base
        * VOL_MULTIPLIERS[vol_bucket]
        * LIQUIDITY_MULTIPLIERS[liquidity_bucket_value]
        * TOD_MULTIPLIERS[tod_bucket]
        * delivery_multiplier
    )
    return SlippageEstimate(
        executable=True,
        slippage_bps=slippage_bps,
        contract_tier=contract_tier,
        volatility_bucket=vol_bucket,
        liquidity_bucket=liquidity_bucket_value,
        time_of_day_bucket=tod_bucket,
        delivery_multiplier_applied=delivery_multiplier > 1,
        recommended_contract_shift=delivery_multiplier > 1,
    )


def volatility_bucket(atr_percentile: float) -> VolatilityBucket:
    if atr_percentile < 0.33:
        return "low"
    if atr_percentile < 0.67:
        return "medium"
    return "high"


def liquidity_bucket(order_size: float, average_daily_volume: float) -> LiquidityBucket:
    if average_daily_volume <= 0:
        return "gte_5pct_adv"
    ratio = abs(order_size) / average_daily_volume
    if ratio < 0.01:
        return "lt_1pct_adv"
    if ratio < 0.05:
        return "pct_1_to_5_adv"
    return "gte_5pct_adv"


def time_of_day_bucket(timestamp: datetime) -> TimeOfDayBucket:
    local_time = timestamp.time()
    if local_time >= time(21, 0) or local_time < time(2, 30):
        return "night"
    if time(9, 0) <= local_time < time(9, 15):
        return "open_15m"
    if time(14, 45) <= local_time <= time(15, 0):
        return "close_15m"
    return "main_session"
