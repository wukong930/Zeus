from datetime import datetime, timedelta, timezone

from app.models.change_review_queue import ChangeReviewQueue
from app.models.signal import SignalTrack
from app.services.calibration.decay_detector import detect_decay
from app.services.calibration.updater import build_calibration_proposal, generate_calibration_reviews


class FakeScalars:
    def __init__(self, rows: list | None = None, first_row=None) -> None:
        self._rows = rows or []
        self._first_row = first_row

    def all(self) -> list:
        return self._rows

    def first(self):
        return self._first_row


class FakeSession:
    def __init__(self, rows: list[SignalTrack]) -> None:
        self.rows = rows
        self.scalar_calls = 0
        self.added: list[object] = []

    async def scalars(self, _) -> FakeScalars:
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            return FakeScalars(rows=self.rows)
        return FakeScalars()

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        return None


def _track(outcome: str, created_at: datetime) -> SignalTrack:
    return SignalTrack(
        signal_type="momentum",
        category="energy",
        confidence=0.8,
        outcome=outcome,
        regime_at_emission="range_low_vol",
        created_at=created_at,
    )


def test_decay_detector_flags_clustered_misses() -> None:
    now = datetime(2026, 5, 3, tzinfo=timezone.utc)
    rows = [_track("hit", now)] * 4 + [_track("miss", now)] * 8

    result = detect_decay(rows, baseline_hit_rate=0.6, threshold=3.0)

    assert result.decay_detected is True
    assert result.cusum_score >= 3.0


def test_build_calibration_proposal_uses_bayesian_weight_and_decay() -> None:
    now = datetime(2026, 5, 3, tzinfo=timezone.utc)
    outcomes = [
        "hit",
        "hit",
        "miss",
        "hit",
        "hit",
        "miss",
        "hit",
        "hit",
        "miss",
        "hit",
        "hit",
        "miss",
        "hit",
        "hit",
        "miss",
        "hit",
        "hit",
        "miss",
        "hit",
        "hit",
    ]
    rows = [_track(outcome, now + timedelta(minutes=idx)) for idx, outcome in enumerate(outcomes)]

    proposal = build_calibration_proposal(
        rows,
        signal_type="momentum",
        category="energy",
        regime="range_low_vol",
    )

    assert proposal.sample_size == 20
    assert proposal.hit_count == 14
    assert round(proposal.rolling_hit_rate or 0, 2) == 0.7
    assert proposal.effective_weight > 1.0
    assert proposal.target_key == "momentum:energy:range_low_vol"


async def test_generate_calibration_reviews_queues_grouped_proposals() -> None:
    now = datetime(2026, 5, 3, tzinfo=timezone.utc)
    rows = [
        _track("hit", now - timedelta(days=idx))
        for idx in range(3)
    ] + [
        _track("miss", now - timedelta(days=idx + 3))
        for idx in range(2)
    ]
    session = FakeSession(rows)

    result = await generate_calibration_reviews(
        session,  # type: ignore[arg-type]
        as_of=now,
        min_samples=1,
    )

    assert result.groups == 1
    assert result.queued == 1
    assert isinstance(session.added[0], ChangeReviewQueue)
    assert session.added[0].target_key == "momentum:energy:range_low_vol"
