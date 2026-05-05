from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.recommendations import require_adoptable_recommendation
from app.models.recommendation import Recommendation


class FakeSession:
    def __init__(self, row: Recommendation | None) -> None:
        self.row = row

    async def get(self, _, __):
        return self.row


def _recommendation(*, status: str = "pending", expires_at: datetime | None = None) -> Recommendation:
    return Recommendation(
        id=uuid4(),
        status=status,
        recommended_action="open_spread",
        legs=[{"asset": "RB", "direction": "long"}],
        priority_score=80,
        portfolio_fit_score=70,
        margin_efficiency_score=75,
        margin_required=10_000,
        reasoning="adoptable recommendation",
        risk_items=[],
        expires_at=expires_at or datetime(2026, 5, 5, tzinfo=timezone.utc),
        entry_price=3200,
    )


async def test_pending_recommendation_can_be_adopted_before_expiry() -> None:
    row = _recommendation()

    result = await require_adoptable_recommendation(
        FakeSession(row),  # type: ignore[arg-type]
        row.id,
        as_of=datetime(2026, 5, 4, tzinfo=timezone.utc),
    )

    assert result is row


async def test_non_pending_recommendation_cannot_be_adopted_again() -> None:
    row = _recommendation(status="accepted")

    with pytest.raises(HTTPException) as exc_info:
        await require_adoptable_recommendation(
            FakeSession(row),  # type: ignore[arg-type]
            row.id,
            as_of=datetime(2026, 5, 4, tzinfo=timezone.utc),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Recommendation is not pending"


async def test_expired_recommendation_cannot_be_adopted() -> None:
    row = _recommendation(expires_at=datetime(2026, 5, 3, tzinfo=timezone.utc))

    with pytest.raises(HTTPException) as exc_info:
        await require_adoptable_recommendation(
            FakeSession(row),  # type: ignore[arg-type]
            row.id,
            as_of=datetime(2026, 5, 4, tzinfo=timezone.utc),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Recommendation has expired"
