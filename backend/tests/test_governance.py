from datetime import datetime, timezone

import pytest

from app.models.change_review_queue import ChangeReviewQueue
from app.models.calibration import SignalCalibration
from app.services.calibration.updater import CalibrationProposal, apply_signal_calibration_change
from app.services.governance.review_queue import ReviewRequiredError


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
