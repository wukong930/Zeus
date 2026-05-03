import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calibration import SignalCalibration
from app.models.signal import SignalTrack

DEFAULT_CALIBRATION_WEIGHT = 1.0


def signal_combination_hash(
    *,
    signal_type: str,
    category: str,
    regime: str | None,
    related_assets: list[str],
) -> str:
    payload = {
        "signal_type": signal_type,
        "category": category,
        "regime": regime or "unknown",
        "related_assets": sorted(related_assets),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def get_calibration_weight(
    session: AsyncSession | None,
    *,
    signal_type: str,
    category: str,
    regime: str | None,
    as_of: datetime | None = None,
) -> float:
    if session is None:
        return DEFAULT_CALIBRATION_WEIGHT

    effective_at = as_of or datetime.now(timezone.utc)
    statement = (
        select(SignalCalibration)
        .where(
            SignalCalibration.signal_type == signal_type,
            SignalCalibration.category == category,
            SignalCalibration.regime == (regime or "unknown"),
            SignalCalibration.effective_from <= effective_at,
            or_(
                SignalCalibration.effective_to.is_(None),
                SignalCalibration.effective_to > effective_at,
            ),
        )
        .order_by(desc(SignalCalibration.effective_from))
        .limit(1)
    )
    row = (await session.scalars(statement)).first()
    if row is not None:
        return row.effective_weight

    fallback_statement = (
        select(SignalCalibration)
        .where(
            SignalCalibration.signal_type == signal_type,
            SignalCalibration.category == category,
            SignalCalibration.regime == "unknown",
            SignalCalibration.effective_from <= effective_at,
            or_(
                SignalCalibration.effective_to.is_(None),
                SignalCalibration.effective_to > effective_at,
            ),
        )
        .order_by(desc(SignalCalibration.effective_from))
        .limit(1)
    )
    fallback = (await session.scalars(fallback_statement)).first()
    return fallback.effective_weight if fallback is not None else DEFAULT_CALIBRATION_WEIGHT


async def track_signal_emission(
    session: AsyncSession | None,
    *,
    signal: dict[str, Any],
    category: str,
    regime: str | None,
    calibration_weight: float,
    position_id: UUID | None = None,
) -> SignalTrack | None:
    if session is None:
        return None

    spread_info = signal.get("spread_info") if isinstance(signal.get("spread_info"), dict) else None
    related_assets = [str(asset) for asset in signal.get("related_assets", [])]
    row = SignalTrack(
        signal_type=str(signal["signal_type"]),
        category=category,
        confidence=float(signal.get("confidence", 0)),
        z_score=float(spread_info["z_score"]) if spread_info is not None else None,
        regime=regime,
        regime_at_emission=regime,
        calibration_weight_at_emission=calibration_weight,
        signal_combination_hash=signal_combination_hash(
            signal_type=str(signal["signal_type"]),
            category=category,
            regime=regime,
            related_assets=related_assets,
        ),
        outcome="pending",
        position_id=position_id,
    )
    session.add(row)
    await session.flush()
    return row
