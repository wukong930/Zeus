"""Cross-sectional reversal forecast — the validated factor as a governed signal.

The investigation found one real, out-of-sample-significant edge: a commodity
cross-sectional reversal factor (rank by trailing momentum, long the losers /
short the winners). This turns it into a production-shaped signal: a
deterministic, point-in-time ``ForecastRecord`` with dollar-neutral target
weights, a ``model_version`` and a ``feature_hash`` of the inputs for full
reproducibility / audit.

``decision_grade`` is ALWAYS False here — the forecast is advisory / shadow. It
must pass governance review + shadow validation before anything may treat it as
authoritative, exactly like any other rule change on the platform. This service
never writes a production trading decision.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.forecast import ForecastRecord
from app.services.backtest.replay import SECTOR_BY_SYMBOL, load_main_series

MODEL_VERSION = "xs_reversal/1.0"
DEFAULT_LOOKBACK = 120
DEFAULT_K = 10


@dataclass(frozen=True, slots=True)
class Forecast:
    as_of: datetime
    signal: str
    model_version: str
    feature_hash: str
    target_weights: dict[str, float]
    universe_size: int


def trailing_momentum(closes: list[float], lookback: int) -> float | None:
    if len(closes) < lookback + 1:
        return None
    base = closes[-lookback - 1]
    if base <= 0 or closes[-1] <= 0:
        return None
    return math.log(closes[-1] / base)


def reversal_weights(momentum_by_symbol: dict[str, float | None], *, k: int) -> dict[str, float]:
    """Long the bottom-k (losers), short the top-k (winners); dollar-neutral."""

    valid = {
        symbol: value
        for symbol, value in momentum_by_symbol.items()
        if value is not None and math.isfinite(value)
    }
    if len(valid) < 2 * k:
        return {}
    ordered = sorted(valid, key=lambda symbol: (valid[symbol], symbol))
    weights: dict[str, float] = {}
    for symbol in ordered[:k]:
        weights[symbol] = round(1.0 / k, 6)  # long losers (reversal)
    for symbol in ordered[-k:]:
        weights[symbol] = round(-1.0 / k, 6)  # short winners
    return weights


def feature_hash(
    as_of: datetime, signal: str, momentum_by_symbol: dict[str, float | None]
) -> str:
    payload = {
        "as_of": as_of.isoformat(),
        "signal": signal,
        "model_version": MODEL_VERSION,
        "momentum": {
            symbol: round(value, 8)
            for symbol, value in sorted(momentum_by_symbol.items())
            if value is not None and math.isfinite(value)
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_forecast(
    as_of: datetime,
    momentum_by_symbol: dict[str, float | None],
    *,
    lookback: int = DEFAULT_LOOKBACK,
    k: int = DEFAULT_K,
) -> Forecast:
    signal = f"xs_reversal_mom{lookback}"
    weights = reversal_weights(momentum_by_symbol, k=k)
    universe = sum(
        1 for value in momentum_by_symbol.values() if value is not None and math.isfinite(value)
    )
    return Forecast(
        as_of=as_of,
        signal=signal,
        model_version=MODEL_VERSION,
        feature_hash=feature_hash(as_of, signal, momentum_by_symbol),
        target_weights=weights,
        universe_size=universe,
    )


async def generate_cross_sectional_forecast(
    session: AsyncSession,
    *,
    as_of: datetime,
    lookback: int = DEFAULT_LOOKBACK,
    k: int = DEFAULT_K,
    symbols: list[str] | None = None,
    persist: bool = True,
) -> ForecastRecord:
    universe = symbols or sorted(SECTOR_BY_SYMBOL)
    momentum: dict[str, float | None] = {}
    for symbol in universe:
        bars = await load_main_series(session, symbol, as_of=as_of)
        closes = [bar.close for bar in bars if bar.timestamp <= as_of]
        momentum[symbol] = trailing_momentum(closes, lookback)

    forecast = build_forecast(as_of, momentum, lookback=lookback, k=k)
    row = ForecastRecord(
        as_of=forecast.as_of,
        signal=forecast.signal,
        model_version=forecast.model_version,
        feature_hash=forecast.feature_hash,
        target_weights=forecast.target_weights,
        universe_size=forecast.universe_size,
        decision_grade=False,  # advisory / shadow until governed
    )
    if persist:
        session.add(row)
        await session.flush()
    return row
