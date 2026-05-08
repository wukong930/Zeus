from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.notebook import (
    NotebookSnapshot,
    entry_from_report,
    load_notebook_snapshot,
    parse_uuid_list,
    string_list,
)
from app.core.database import get_db
from app.main import create_app
from app.models.alert import Alert
from app.models.learning_hypotheses import LearningHypothesis
from app.models.research import ResearchHypothesis, ResearchReport


class FakeScalarResult:
    def __init__(self, rows) -> None:
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, batches) -> None:
        self.batches = list(batches)
        self.scalars_count = 0

    async def scalars(self, _statement):
        self.scalars_count += 1
        return FakeScalarResult(self.batches.pop(0))


def test_report_entry_uses_real_alert_references() -> None:
    report = _report()
    alert = _alert(related_research_id=report.id)

    entry = entry_from_report(report, {report.id: [alert]})

    assert entry.kind == "report"
    assert entry.folder == "研究报告"
    assert entry.references[0].id == alert.id
    assert entry.references[0].type == "alert"
    assert entry.references[0].relation == "related_alert"


async def test_notebook_snapshot_merges_runtime_research_rows() -> None:
    report = _report(published_at=datetime(2026, 5, 3, tzinfo=timezone.utc))
    learning = _learning_hypothesis(created_at=datetime(2026, 5, 5, tzinfo=timezone.utc))
    research = _research_hypothesis(created_at=datetime(2026, 5, 4, tzinfo=timezone.utc))
    alert = _alert(related_research_id=report.id)
    session = FakeSession([[report], [learning], [research], [alert]])

    snapshot = await load_notebook_snapshot(session, limit=10)  # type: ignore[arg-type]

    assert [note.kind for note in snapshot.notes] == [
        "learning_hypothesis",
        "research_hypothesis",
        "report",
    ]
    assert {folder.name: folder.count for folder in snapshot.folders} == {
        "学习假设": 1,
        "研究假设": 1,
        "研究报告": 1,
    }
    assert snapshot.reference_counts["alerts"] == 1
    assert session.scalars_count == 4


def test_parse_uuid_list_ignores_bad_values() -> None:
    valid = uuid4()

    assert parse_uuid_list([str(valid), "bad", None]) == [valid]


def test_parse_uuid_list_caps_reference_count() -> None:
    values = [str(uuid4()) for _ in range(105)]

    assert len(parse_uuid_list(values)) == 100


def test_notebook_entry_caps_tags_and_alert_references() -> None:
    report = _report()
    report.hypotheses = [f"hypothesis-{index}" for index in range(30)]
    alerts = [_alert(related_research_id=report.id) for _ in range(25)]

    entry = entry_from_report(report, {report.id: alerts})

    assert len(entry.tags) == 20
    assert entry.tags[0] == "daily"
    assert len(entry.references) == 20


def test_string_list_trims_truncates_and_caps_items() -> None:
    values = ["  alpha  ", "", "x" * 350, *[f"item-{index}" for index in range(25)]]

    rows = string_list(values)

    assert rows[0] == "alpha"
    assert len(rows[1]) == 300
    assert len(rows) == 20


def test_notebook_route_is_registered(monkeypatch) -> None:
    async def fake_db():
        yield object()

    async def fake_snapshot(_session, *, limit: int = 100):
        return NotebookSnapshot(
            generated_at=datetime(2026, 5, 7, tzinfo=timezone.utc),
            source="database",
            notes=[],
            folders=[],
            reference_counts={"alerts": 0, "hypotheses": 0, "reports": 0},
        )

    monkeypatch.setattr("app.api.notebook.load_notebook_snapshot", fake_snapshot)
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.get("/api/notebook")

    assert response.status_code == 200
    assert response.json()["source"] == "database"
    assert response.json()["notes"] == []


def _report(*, published_at: datetime | None = None) -> ResearchReport:
    return ResearchReport(
        id=uuid4(),
        type="daily",
        title="Rubber chain research",
        summary="NR/RU spread pressure",
        body="Runtime report body",
        hypotheses=["rubber"],
        related_strategy_ids=[],
        related_alert_ids=[],
        published_at=published_at or datetime(2026, 5, 1, tzinfo=timezone.utc),
    )


def _learning_hypothesis(*, created_at: datetime | None = None) -> LearningHypothesis:
    return LearningHypothesis(
        id=uuid4(),
        hypothesis="Momentum weakens after high-volatility regime shifts.",
        supporting_evidence=["Recent misses clustered in ferrous."],
        proposed_change="Shadow test stricter momentum threshold.",
        confidence=0.7,
        sample_size=12,
        counterevidence=[],
        status="proposed",
        evidence_strength="medium_evidence",
        source_payload={},
        created_at=created_at or datetime(2026, 5, 1, tzinfo=timezone.utc),
        updated_at=created_at or datetime(2026, 5, 1, tzinfo=timezone.utc),
    )


def _research_hypothesis(*, created_at: datetime | None = None) -> ResearchHypothesis:
    return ResearchHypothesis(
        id=uuid4(),
        title="Inventory divergence",
        description="Inventory divergence may lead curve steepening.",
        confidence=0.6,
        status="new",
        created_at=created_at or datetime(2026, 5, 1, tzinfo=timezone.utc),
    )


def _alert(*, related_research_id=None) -> Alert:
    return Alert(
        id=uuid4(),
        title="Rubber alert",
        summary="Cross-market pressure increased.",
        severity="high",
        category="spread",
        type="spread_anomaly",
        status="active",
        triggered_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
        confidence=0.8,
        adversarial_passed=True,
        related_assets=["NR", "RU"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
        related_research_id=related_research_id,
    )
