from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shadow_runs import ShadowRun
from app.services.shadow.runner import create_shadow_run


@dataclass(frozen=True)
class ShadowApplicationSpec:
    name: str
    algorithm_version: str
    config_diff: dict[str, Any]
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def initial_shadow_application_specs() -> list[ShadowApplicationSpec]:
    return [
        ShadowApplicationSpec(
            name="calibration-prior-alpha2-beta6",
            algorithm_version="phase9-calibration-prior",
            config_diff={"calibration_prior_override": {"alpha_prior": 2.0, "beta_prior": 6.0}},
            notes="Compare more conservative Bayesian calibration priors against production.",
        ),
        ShadowApplicationSpec(
            name="adversarial-jaccard-0.6",
            algorithm_version="phase9-adversarial-jaccard",
            config_diff={"historical_combo_min_similarity": 0.6},
            notes="Compare looser historical-combo similarity threshold.",
        ),
        ShadowApplicationSpec(
            name="adversarial-jaccard-0.8",
            algorithm_version="phase9-adversarial-jaccard",
            config_diff={"historical_combo_min_similarity": 0.8},
            notes="Compare stricter historical-combo similarity threshold.",
        ),
        ShadowApplicationSpec(
            name="news-event-severity-ge-2",
            algorithm_version="phase9-news-severity",
            config_diff={"news_event_min_severity": 2},
            notes="Compare lower news_event severity threshold.",
        ),
        ShadowApplicationSpec(
            name="news-event-severity-ge-3",
            algorithm_version="phase9-news-severity",
            config_diff={"news_event_min_severity": 3},
            notes="Compare production-like news_event severity threshold.",
        ),
    ]


async def create_initial_shadow_applications(
    session: AsyncSession,
    *,
    created_by: str | None = None,
    as_of: datetime | None = None,
    days: int = 30,
) -> list[ShadowRun]:
    started_at = as_of or datetime.now(timezone.utc)
    ended_at = started_at + timedelta(days=days)
    specs = initial_shadow_application_specs()
    existing = {
        row.name: row
        for row in (
            await session.scalars(
                select(ShadowRun).where(
                    ShadowRun.name.in_([spec.name for spec in specs]),
                    ShadowRun.status == "active",
                )
            )
        ).all()
    }
    rows: list[ShadowRun] = []
    for spec in specs:
        if spec.name in existing:
            rows.append(existing[spec.name])
            continue
        rows.append(
            await create_shadow_run(
                session,
                name=spec.name,
                algorithm_version=spec.algorithm_version,
                config_diff=spec.config_diff,
                created_by=created_by,
                notes=spec.notes,
                started_at=started_at,
                ended_at=ended_at,
            )
        )
    return rows
