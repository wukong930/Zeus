from datetime import datetime, timezone
from uuid import uuid4

from app.core.events import ZeusEvent
from app.models.change_review_queue import ChangeReviewQueue
from app.models.shadow_runs import ShadowRun
from app.models.shadow_signals import ShadowSignal
from app.models.signal import SignalTrack
from app.services.alert_agent.config import ConfidenceThresholds
from app.services.calibration.threshold_calibrator import (
    build_threshold_calibration_report,
    enqueue_threshold_review,
)
from app.services.shadow.comparator import build_shadow_comparison_report
from app.services.shadow.runner import run_shadow_for_event, shadow_threshold_config


class FakeScalars:
    def first(self):
        return None


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


def _run(config_diff: dict | None = None) -> ShadowRun:
    return ShadowRun(
        id=uuid4(),
        name="threshold-v2",
        algorithm_version="phase9-threshold-v2",
        config_diff=config_diff or {"confidence_thresholds": {"notify": 0.7}},
        status="active",
        started_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
    )


def _track(confidence: float, outcome: str, signal_type: str = "momentum") -> SignalTrack:
    return SignalTrack(
        signal_type=signal_type,
        category="ferrous",
        confidence=confidence,
        outcome=outcome,
        created_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
    )


async def test_shadow_runner_records_scored_signal_without_publishing_alert() -> None:
    session = FakeSession()
    event = ZeusEvent(
        channel="signal.scored",
        payload={
            "signal": {
                "signal_type": "momentum",
                "category": "ferrous",
                "confidence": 0.74,
                "related_assets": ["RB"],
            },
            "context": {"category": "ferrous", "regime": "range_low_vol"},
            "score": {"combined": 72, "priority": 74},
            "signal_track_id": str(uuid4()),
        },
        timestamp=datetime(2026, 5, 4, tzinfo=timezone.utc),
    )

    result = await run_shadow_for_event(session, _run(), event)  # type: ignore[arg-type]

    assert result.scanned == 1
    assert result.would_emit == 1
    assert isinstance(session.rows[0], ShadowSignal)
    assert session.rows[0].symbol == "RB"
    assert session.rows[0].would_emit is True
    assert session.flush_count == 1


def test_shadow_threshold_config_clamps_experiment_values() -> None:
    config = shadow_threshold_config(
        {"confidence_thresholds": {"notify": 2.0}, "min_combined_score": 120}
    )

    assert config.min_confidence == 1.0
    assert config.min_combined_score == 100.0


def test_threshold_calibrator_builds_reliability_curve_and_suggestions() -> None:
    rows = (
        [_track(0.90, "hit") for _ in range(6)]
        + [_track(0.65, "hit") for _ in range(4)]
        + [_track(0.65, "miss") for _ in range(4)]
        + [_track(0.35, "hit")]
        + [_track(0.35, "miss") for _ in range(7)]
    )

    report = build_threshold_calibration_report(
        rows,
        current_thresholds=ConfidenceThresholds(auto=0.85, notify=0.60),
        min_samples=5,
        target_auto_hit_rate=0.75,
        target_notify_hit_rate=0.55,
    )

    assert report.samples == 22
    assert report.hits == 11
    assert report.suggested_thresholds == {"auto": 0.9, "notify": 0.65}
    assert report.review_required is True
    assert report.bins[3].samples == 8
    assert report.isotonic_curve[-1].calibrated_probability == 1.0


async def test_threshold_review_is_queued_without_config_write() -> None:
    session = FakeSession()
    report = build_threshold_calibration_report(
        [_track(0.90, "hit") for _ in range(5)] + [_track(0.40, "miss") for _ in range(5)],
        current_thresholds=ConfidenceThresholds(auto=0.85, notify=0.60),
        min_samples=3,
        target_auto_hit_rate=0.75,
        target_notify_hit_rate=0.55,
    )

    row = await enqueue_threshold_review(session, report)  # type: ignore[arg-type]

    assert isinstance(row, ChangeReviewQueue)
    assert row.target_table == "alert_agent_config"
    assert row.target_key == "confidence_thresholds"
    assert row.proposed_change["value"]["auto"] == 0.9
    assert session.flush_count == 1


def test_shadow_comparator_reports_shadow_only_delta() -> None:
    run = _run()
    shadow_rows = [
        ShadowSignal(
            shadow_run_id=run.id,
            source_event_type="signal.scored",
            signal_type="momentum",
            category="ferrous",
            symbol="RB",
            would_emit=True,
            confidence=0.8,
            score=72,
        ),
        ShadowSignal(
            shadow_run_id=run.id,
            source_event_type="signal.scored",
            signal_type="news_event",
            category="rubber",
            symbol="RU",
            would_emit=True,
            confidence=0.7,
            score=68,
        ),
    ]
    production_rows = [_track(0.82, "pending")]

    report = build_shadow_comparison_report(
        run,
        shadow_rows=shadow_rows,
        production_rows=production_rows,
    )

    assert report.matched_emit == 1
    assert report.shadow_only == 1
    assert report.production_only == 0
    assert report.sample_cases[0].kind == "shadow_only"
