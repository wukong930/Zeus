from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.api.notebook import (
    NotebookSnapshot,
    _learning_hypotheses_statement,
    _report_alerts_statement,
    _research_hypotheses_statement,
    _research_reports_statement,
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


async def test_notebook_snapshot_accepts_cursor() -> None:
    report = _report(published_at=datetime(2026, 5, 3, tzinfo=timezone.utc))
    learning = _learning_hypothesis(created_at=datetime(2026, 5, 5, tzinfo=timezone.utc))
    research = _research_hypothesis(created_at=datetime(2026, 5, 4, tzinfo=timezone.utc))
    session = FakeSession([[report], [learning], [research], []])

    snapshot = await load_notebook_snapshot(
        session,  # type: ignore[arg-type]
        limit=10,
        before=datetime(2026, 5, 6, tzinfo=timezone.utc),
        before_id=learning.id,
        before_kind="learning_hypothesis",
    )

    assert len(snapshot.notes) == 3
    assert session.scalars_count == 4


def test_notebook_statements_use_cursor_and_stable_order() -> None:
    before = datetime(2026, 5, 6, tzinfo=timezone.utc)
    report_id = uuid4()
    alert_id = uuid4()
    learning_id = uuid4()
    research_id = uuid4()
    report_sql = _compile_postgres(
        _research_reports_statement(
            before=before,
            before_id=report_id,
            before_kind="report",
            limit=20,
        )
    )
    learning_sql = _compile_postgres(
        _learning_hypotheses_statement(
            before=before,
            before_id=learning_id,
            before_kind="learning_hypothesis",
            limit=20,
        )
    )
    research_sql = _compile_postgres(
        _research_hypotheses_statement(
            before=before,
            before_id=research_id,
            before_kind="research_hypothesis",
            limit=20,
        )
    )
    report_alert_sql = _compile_postgres(
        _report_alerts_statement(
            report_ids={report_id},
            related_alert_ids={alert_id},
            limit=500,
        )
    )

    assert "research_reports.published_at <" in report_sql
    assert "research_reports.id <" in report_sql
    assert "ORDER BY research_reports.published_at DESC, research_reports.id DESC" in report_sql
    assert "learning_hypotheses.updated_at <" in learning_sql
    assert "learning_hypotheses.id <" in learning_sql
    assert "ORDER BY learning_hypotheses.updated_at DESC, learning_hypotheses.id DESC" in learning_sql
    assert "research_hypotheses.created_at <" in research_sql
    assert "research_hypotheses.id <" in research_sql
    assert "ORDER BY research_hypotheses.created_at DESC, research_hypotheses.id DESC" in research_sql
    assert "alerts.id IN" in report_alert_sql
    assert "alerts.related_research_id IN" in report_alert_sql
    assert "ORDER BY alerts.triggered_at DESC, alerts.id DESC" in report_alert_sql
    assert "LIMIT" in report_sql


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
    captured: dict[str, object] = {}
    before_id = uuid4()

    async def fake_db():
        yield object()

    async def fake_snapshot(
        _session,
        *,
        limit: int = 100,
        before=None,
        before_id=None,
        before_kind=None,
    ):
        captured["limit"] = limit
        captured["before"] = before
        captured["before_id"] = before_id
        captured["before_kind"] = before_kind
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

    response = client.get(
        "/api/notebook"
        f"?limit=7&before=2026-05-06T00:00:00Z&before_id={before_id}"
        "&before_kind=learning_hypothesis"
    )

    assert response.status_code == 200
    assert captured == {
        "limit": 7,
        "before": datetime(2026, 5, 6, tzinfo=timezone.utc),
        "before_id": before_id,
        "before_kind": "learning_hypothesis",
    }
    assert response.json()["source"] == "database"
    assert response.json()["notes"] == []


def test_notebook_route_rejects_invalid_cursor() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/notebook?before=not-a-date")

    assert response.status_code == 422

    response = client.get(f"/api/notebook?before_id={uuid4()}&before_kind=trade")

    assert response.status_code == 422


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


def _compile_postgres(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))
