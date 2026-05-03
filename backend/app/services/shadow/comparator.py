from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shadow_runs import ShadowRun
from app.models.shadow_signals import ShadowSignal
from app.models.signal import SignalTrack
from app.services.calibration.hit_rate import HIT_OUTCOMES, MISS_OUTCOMES


@dataclass(frozen=True)
class ShadowComparisonCase:
    kind: str
    signal_type: str
    category: str
    symbol: str | None
    confidence: float | None
    score: float | None
    reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ShadowComparisonReport:
    shadow_run_id: str
    algorithm_version: str
    production_total: int
    shadow_total: int
    shadow_would_emit: int
    matched_emit: int
    production_only: int
    shadow_only: int
    production_hit_rate: float | None
    shadow_hit_rate: float | None
    hit_rate_delta: float | None
    disagreement_rate: float
    sample_cases: list[ShadowComparisonCase]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sample_cases"] = [case.to_dict() for case in self.sample_cases]
        return payload


async def compare_shadow_run(
    session: AsyncSession,
    run_id: UUID,
    *,
    as_of: datetime | None = None,
    sample_limit: int = 10,
) -> ShadowComparisonReport | None:
    run = await session.get(ShadowRun, run_id)
    if run is None:
        return None

    effective_end = run.ended_at or as_of or datetime.now(timezone.utc)
    shadow_rows = list(
        (
            await session.scalars(
                select(ShadowSignal)
                .where(ShadowSignal.shadow_run_id == run_id)
                .order_by(ShadowSignal.created_at.asc())
            )
        ).all()
    )
    production_rows = list(
        (
            await session.scalars(
                select(SignalTrack)
                .where(
                    SignalTrack.created_at >= run.started_at,
                    SignalTrack.created_at <= effective_end,
                )
                .order_by(SignalTrack.created_at.asc())
            )
        ).all()
    )
    return build_shadow_comparison_report(
        run,
        shadow_rows=shadow_rows,
        production_rows=production_rows,
        sample_limit=sample_limit,
    )


def build_shadow_comparison_report(
    run: ShadowRun,
    *,
    shadow_rows: list[ShadowSignal],
    production_rows: list[SignalTrack],
    sample_limit: int = 10,
) -> ShadowComparisonReport:
    production_counts = Counter(_production_key(row) for row in production_rows)
    shadow_emit_rows = [row for row in shadow_rows if row.would_emit]
    shadow_counts = Counter(_shadow_key(row) for row in shadow_emit_rows)
    all_keys = set(production_counts) | set(shadow_counts)
    matched = sum(min(production_counts[key], shadow_counts[key]) for key in all_keys)
    production_only = sum(max(0, production_counts[key] - shadow_counts[key]) for key in all_keys)
    shadow_only = sum(max(0, shadow_counts[key] - production_counts[key]) for key in all_keys)
    denominator = max(1, len(production_rows) + len(shadow_emit_rows) - matched)
    production_hit_rate = _hit_rate([row.outcome for row in production_rows])
    shadow_hit_rate = _hit_rate([row.outcome for row in shadow_rows if row.outcome is not None])
    sample_cases = _sample_cases(
        production_counts=production_counts,
        shadow_counts=shadow_counts,
        shadow_rows=shadow_emit_rows,
        production_rows=production_rows,
        limit=sample_limit,
    )
    return ShadowComparisonReport(
        shadow_run_id=str(run.id),
        algorithm_version=run.algorithm_version,
        production_total=len(production_rows),
        shadow_total=len(shadow_rows),
        shadow_would_emit=len(shadow_emit_rows),
        matched_emit=matched,
        production_only=production_only,
        shadow_only=shadow_only,
        production_hit_rate=production_hit_rate,
        shadow_hit_rate=shadow_hit_rate,
        hit_rate_delta=(
            round(shadow_hit_rate - production_hit_rate, 4)
            if production_hit_rate is not None and shadow_hit_rate is not None
            else None
        ),
        disagreement_rate=round((production_only + shadow_only) / denominator, 4),
        sample_cases=sample_cases,
    )


def _sample_cases(
    *,
    production_counts: Counter[tuple[str, str]],
    shadow_counts: Counter[tuple[str, str]],
    shadow_rows: list[ShadowSignal],
    production_rows: list[SignalTrack],
    limit: int,
) -> list[ShadowComparisonCase]:
    cases: list[ShadowComparisonCase] = []
    shadow_only_keys = {
        key
        for key, count in shadow_counts.items()
        if count > production_counts.get(key, 0)
    }
    for row in shadow_rows:
        if len(cases) >= limit:
            break
        if _shadow_key(row) not in shadow_only_keys:
            continue
        cases.append(
            ShadowComparisonCase(
                kind="shadow_only",
                signal_type=row.signal_type,
                category=row.category,
                symbol=row.symbol,
                confidence=row.confidence,
                score=row.score,
                reason=row.reason,
            )
        )

    production_only_keys = {
        key
        for key, count in production_counts.items()
        if count > shadow_counts.get(key, 0)
    }
    for row in production_rows:
        if len(cases) >= limit:
            break
        if _production_key(row) not in production_only_keys:
            continue
        cases.append(
            ShadowComparisonCase(
                kind="production_only",
                signal_type=row.signal_type,
                category=row.category,
                symbol=None,
                confidence=row.confidence,
                score=None,
                reason=row.outcome,
            )
        )
    return cases


def _shadow_key(row: ShadowSignal) -> tuple[str, str]:
    return row.signal_type, row.category


def _production_key(row: SignalTrack) -> tuple[str, str]:
    return row.signal_type, row.category


def _hit_rate(outcomes: list[str]) -> float | None:
    hits = 0
    misses = 0
    for outcome in outcomes:
        normalized = outcome.lower()
        if normalized in HIT_OUTCOMES:
            hits += 1
        elif normalized in MISS_OUTCOMES:
            misses += 1
    total = hits + misses
    return round(hits / total, 4) if total else None
