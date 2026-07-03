from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.api.governance import change_reviews_statement
from app.core.database import get_db
from app.main import create_app
from app.models.change_review_queue import ChangeReviewQueue
from app.models.calibration import SignalCalibration
from app.services.calibration.updater import CalibrationProposal, apply_signal_calibration_change
from app.services.governance.review_queue import (
    ReviewRequiredError,
    _active_review_lookup_statement,
)


class FakeScalars:
    def __init__(self, row=None) -> None:
        self._row = row

    def first(self):
        return self._row


class FakeSession:
    def __init__(self) -> None:
        self.rows: list[object] = []
        self.flush_count = 0

    async def scalars(self, _) -> FakeScalars:
        return FakeScalars()

    def add(self, row: object) -> None:
        self.rows.append(row)

    async def flush(self) -> None:
        self.flush_count += 1


def _proposal() -> CalibrationProposal:
    return CalibrationProposal(
        signal_type="momentum",
        category="energy",
        regime="range_low_vol",
        base_weight=1.0,
        effective_weight=1.2,
        rolling_hit_rate=0.6,
        sample_size=20,
        hit_count=12,
        miss_count=8,
        alpha_prior=4.0,
        beta_prior=4.0,
        decay_detected=False,
        decay_score=0.0,
        prior_dominant=False,
    )


async def test_review_required_blocks_unapproved_calibration_write() -> None:
    session = FakeSession()
    proposal = _proposal()

    with pytest.raises(ReviewRequiredError):
        await apply_signal_calibration_change(
            session,  # type: ignore[arg-type]
            proposal,
            proposed_change=proposal.to_change(),
            review_source="calibration",
            target_key=proposal.target_key,
        )

    assert isinstance(session.rows[0], ChangeReviewQueue)
    assert session.rows[0].target_table == "signal_calibration"
    assert session.rows[0].target_key == "momentum:energy:range_low_vol"
    assert session.flush_count == 1


async def test_review_required_allows_human_approved_calibration_write() -> None:
    session = FakeSession()
    proposal = _proposal()
    applied_at = datetime(2026, 5, 3, tzinfo=timezone.utc)

    row = await apply_signal_calibration_change(
        session,  # type: ignore[arg-type]
        proposal,
        human_approved=True,
        applied_at=applied_at,
    )

    assert isinstance(row, SignalCalibration)
    assert row.effective_weight == 1.2
    assert row.effective_from == applied_at
    assert session.rows[0] is row


class FakeGovernanceApiSession:
    def __init__(self, row: ChangeReviewQueue | None) -> None:
        self.row = row
        self.commit_count = 0
        self.refresh_count = 0

    async def get(self, model, row_id):
        if model is ChangeReviewQueue and self.row is not None and self.row.id == row_id:
            return self.row
        return None

    async def commit(self) -> None:
        self.commit_count += 1

    async def refresh(self, row) -> None:
        self.refresh_count += 1


def test_governance_decision_api_marks_pending_review() -> None:
    review_id = uuid4()
    row = ChangeReviewQueue(
        id=review_id,
        source="calibration",
        target_table="signal_calibration",
        target_key="momentum:energy:range_low_vol",
        proposed_change={"base_weight": 1.0},
        status="pending",
        reason="Shadow result requires review.",
        created_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
    )
    session = FakeGovernanceApiSession(row)

    async def fake_db():
        yield session

    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.post(
        f"/api/governance/reviews/{review_id}/decision",
        json={"decision": "approve", "reviewed_by": "operator", "note": "looks good"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approved"
    assert payload["reviewed_by"] == "operator"
    assert payload["proposed_change"]["review_decision"]["production_effect"] == "none"
    assert session.commit_count == 1
    assert session.refresh_count == 1


def test_governance_decision_api_rejects_redeciding_review() -> None:
    review_id = uuid4()
    row = ChangeReviewQueue(
        id=review_id,
        source="calibration",
        target_table="signal_calibration",
        target_key="momentum:energy:range_low_vol",
        proposed_change={"base_weight": 1.0},
        status="approved",
        created_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
    )
    session = FakeGovernanceApiSession(row)

    async def fake_db():
        yield session

    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.post(
        f"/api/governance/reviews/{review_id}/decision",
        json={"decision": "reject", "reviewed_by": "operator"},
    )

    assert response.status_code == 409
    assert session.commit_count == 0


def test_governance_api_rejects_invalid_filters_and_decisions() -> None:
    client = TestClient(create_app())

    invalid_filter = client.get("/api/governance/reviews?status=published")
    invalid_cursor = client.get("/api/governance/reviews?before=not-a-date")
    invalid_decision = client.post(
        f"/api/governance/reviews/{uuid4()}/decision",
        json={"decision": "publish"},
    )

    assert invalid_filter.status_code == 422
    assert invalid_cursor.status_code == 422
    assert invalid_decision.status_code == 422


def test_change_reviews_statement_pushes_triage_filters_and_cursor_to_database() -> None:
    sql = str(
        change_reviews_statement(
            status_filter="shadow_review",
            source="event_intelligence",
            target_table="event_intelligence_items",
            triage_tier="shadow_review",
            min_attention_score=45,
            requires_human_attention=False,
            before=datetime(2026, 5, 18, 12, tzinfo=timezone.utc),
            before_id=uuid4(),
            limit=50,
        ).compile(dialect=postgresql.dialect())
    )

    assert "change_review_queue.status =" in sql
    assert "change_review_queue.source =" in sql
    assert "change_review_queue.target_table =" in sql
    assert "proposed_change" in sql
    assert "CAST" in sql
    assert "BOOLEAN" in sql
    assert "change_review_queue.created_at <" in sql
    assert "change_review_queue.id <" in sql
    assert "ORDER BY change_review_queue.created_at DESC, change_review_queue.id DESC" in sql
    assert "LIMIT" in sql


def test_active_review_lookup_statement_uses_stable_oldest_order() -> None:
    sql = str(
        _active_review_lookup_statement(
            source="calibration",
            target_table="signal_calibration",
            target_key="momentum:energy:range_low_vol",
            statuses=("pending", "shadow_review", "pending"),
        ).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "change_review_queue.source = 'calibration'" in sql
    assert "change_review_queue.target_table = 'signal_calibration'" in sql
    assert "change_review_queue.target_key = 'momentum:energy:range_low_vol'" in sql
    assert "change_review_queue.status IN ('pending', 'shadow_review')" in sql
    assert "ORDER BY change_review_queue.created_at ASC, change_review_queue.id ASC" in sql
    assert "LIMIT 1" in sql
