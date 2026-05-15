from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adversarial import AdversarialResult
from app.models.calibration import SignalCalibration
from app.services.adversarial.historical_combo import (
    HistoricalComboCandidate,
    evaluate_historical_combo,
    fuzzy_combo_hash,
)
from app.services.adversarial.null_hypothesis import (
    evaluate_null_hypothesis,
    latest_null_distribution_cache,
)
from app.services.adversarial.runtime import load_adversarial_runtime_config
from app.services.adversarial.structural_counter import (
    evaluate_structural_counter,
    load_structural_edges,
)
from app.services.adversarial.types import (
    AdversarialCheckResult,
    MODE_ENFORCING,
    MODE_INFORMATIONAL,
)

CONFIDENCE_PENALTY = 0.7


@dataclass(frozen=True)
class AdversarialDecision:
    passed: bool
    suppressed: bool
    confidence_multiplier: float
    adjusted_signal: dict[str, Any]
    results: list[AdversarialCheckResult]
    signal_combination_hash: str
    runtime_mode: str = "warmup"
    warmup_enabled: bool = True
    result_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "suppressed": self.suppressed,
            "confidence_multiplier": self.confidence_multiplier,
            "signal_combination_hash": self.signal_combination_hash,
            "runtime_mode": self.runtime_mode,
            "warmup_enabled": self.warmup_enabled,
            "result_id": self.result_id,
            "checks": [result.to_dict() for result in self.results],
        }


async def evaluate_adversarial_signal(
    session: AsyncSession | None,
    *,
    signal: dict[str, Any],
    context: dict[str, Any],
    correlation_id: str | None = None,
    as_of: datetime | None = None,
) -> AdversarialDecision:
    effective_as_of = as_of or datetime.now(timezone.utc)
    signal_type = str(signal["signal_type"])
    category = str(context.get("category") or signal.get("category") or "unknown")
    regime = str(context.get("regime") or context.get("regime_at_emission") or "unknown")
    signal_types = signal_type_set(signal, context)
    combination_hash = fuzzy_combo_hash(
        signal_types=signal_types,
        category=category,
        regime=regime,
    )
    runtime_config = await load_adversarial_runtime_config(session)

    null_cache = (
        await latest_null_distribution_cache(
            session,
            signal_type=signal_type,
            category=category,
            as_of=effective_as_of,
        )
        if session is not None
        else None
    )
    null_result = evaluate_null_hypothesis(signal, null_cache)
    historical_result = evaluate_historical_combo(
        signal_types=signal_types,
        category=category,
        regime=regime,
        candidates=(
            await load_historical_combo_candidates(
                session,
                category=category,
                regime=regime,
            )
            if session is not None
            else []
        ),
        force_mode=MODE_INFORMATIONAL if runtime_config.warmup_enabled else None,
    )
    structural_result = evaluate_structural_counter(
        signal=signal,
        context=context,
        edges=(
            await load_structural_edges(session, symbols=related_assets(signal))
            if session is not None
            else []
        ),
    )

    decision = decide_adversarial_outcome(
        signal=signal,
        results=[null_result, historical_result, structural_result],
        signal_combination_hash=combination_hash,
        runtime_mode=runtime_config.mode,
        warmup_enabled=runtime_config.warmup_enabled,
    )
    if session is None:
        return decision

    row = await record_adversarial_decision(
        session,
        decision,
        signal_type=signal_type,
        category=category,
        regime=regime,
        correlation_id=correlation_id,
    )
    return AdversarialDecision(
        passed=decision.passed,
        suppressed=decision.suppressed,
        confidence_multiplier=decision.confidence_multiplier,
        adjusted_signal=decision.adjusted_signal,
        results=decision.results,
        signal_combination_hash=decision.signal_combination_hash,
        runtime_mode=decision.runtime_mode,
        warmup_enabled=decision.warmup_enabled,
        result_id=str(row.id),
    )


def decide_adversarial_outcome(
    *,
    signal: dict[str, Any],
    results: list[AdversarialCheckResult],
    signal_combination_hash: str,
    runtime_mode: str = "warmup",
    warmup_enabled: bool = True,
) -> AdversarialDecision:
    enforced_failures = [result for result in results if result.enforcing_failure]
    all_failed = all(not result.passed for result in results)
    all_failures_enforcing = all(result.mode == MODE_ENFORCING for result in results)
    suppressed = all_failed and all_failures_enforcing
    confidence_multiplier = 1.0
    if suppressed:
        confidence_multiplier = 0.0
    elif enforced_failures:
        confidence_multiplier = CONFIDENCE_PENALTY

    adjusted_signal = dict(signal)
    if confidence_multiplier not in {0.0, 1.0}:
        adjusted_signal["confidence"] = max(
            0.0,
            min(1.0, float(signal.get("confidence", 0)) * confidence_multiplier),
        )
        adjusted_signal["summary"] = str(signal.get("summary", "")).strip()

    return AdversarialDecision(
        passed=not enforced_failures and not suppressed,
        suppressed=suppressed,
        confidence_multiplier=confidence_multiplier,
        adjusted_signal=adjusted_signal,
        results=results,
        signal_combination_hash=signal_combination_hash,
        runtime_mode=runtime_mode,
        warmup_enabled=warmup_enabled,
    )


async def record_adversarial_decision(
    session: AsyncSession,
    decision: AdversarialDecision,
    *,
    signal_type: str,
    category: str,
    regime: str,
    correlation_id: str | None = None,
) -> AdversarialResult:
    null_result = _result_by_name(decision.results, "null_hypothesis")
    historical_result = _result_by_name(decision.results, "historical_combo")
    structural_result = _result_by_name(decision.results, "structural_counter")
    row = AdversarialResult(
        signal_type=signal_type,
        category=category,
        regime=regime,
        signal_combination_hash=decision.signal_combination_hash,
        correlation_id=correlation_id,
        null_hypothesis_pvalue=null_result.score if null_result is not None else None,
        null_hypothesis_passed=null_result.passed if null_result is not None else None,
        historical_combo_hit_rate=(
            historical_result.score if historical_result is not None else None
        ),
        historical_combo_sample_size=(
            historical_result.sample_size if historical_result is not None else 0
        ),
        historical_combo_mode=(
            historical_result.mode if historical_result is not None else "informational"
        ),
        historical_combo_passed=historical_result.passed if historical_result is not None else None,
        structural_counter_count=(
            structural_result.sample_size if structural_result is not None else 0
        ),
        structural_counter_passed=structural_result.passed if structural_result is not None else None,
        passed=decision.passed,
        suppressed=decision.suppressed,
        confidence_multiplier=decision.confidence_multiplier,
        details=decision.to_payload(),
    )
    session.add(row)
    await session.flush()
    return row


async def attach_signal_track_to_adversarial_result(
    session: AsyncSession,
    *,
    result_id: str | None,
    signal_track_id: Any,
) -> None:
    if result_id is None or signal_track_id is None:
        return
    row = await session.get(AdversarialResult, UUID(str(result_id)))
    if row is not None:
        row.signal_track_id = signal_track_id


async def load_historical_combo_candidates(
    session: AsyncSession,
    *,
    category: str,
    regime: str,
) -> list[HistoricalComboCandidate]:
    rows = (
        await session.scalars(
            select(SignalCalibration).where(
                SignalCalibration.category == category,
                SignalCalibration.regime.in_([regime, "unknown"]),
            )
        )
    ).all()
    return [
        HistoricalComboCandidate(
            signal_types=frozenset([row.signal_type]),
            category=row.category,
            regime=row.regime,
            hit_rate=row.rolling_hit_rate,
            sample_size=row.sample_size,
        )
        for row in rows
    ]


def signal_type_set(signal: dict[str, Any], context: dict[str, Any]) -> frozenset[str]:
    signal_types = context.get("signal_types") or context.get("signal_type_set")
    if isinstance(signal_types, (list, tuple, set)):
        values = {str(item) for item in signal_types if str(item)}
        if values:
            return frozenset(values)
    return frozenset([str(signal["signal_type"])])


def related_assets(signal: dict[str, Any]) -> list[str]:
    return [str(asset) for asset in signal.get("related_assets", [])]


def _result_by_name(
    results: list[AdversarialCheckResult],
    name: str,
) -> AdversarialCheckResult | None:
    for result in results:
        if result.check_name == name:
            return result
    return None
