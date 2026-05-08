from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.alert import Alert
from app.models.learning_hypotheses import LearningHypothesis
from app.models.research import ResearchHypothesis, ResearchReport

router = APIRouter(prefix="/api/notebook", tags=["notebook"])

MAX_NOTEBOOK_REFERENCES_PER_ENTRY = 20
MAX_NOTEBOOK_TAGS = 20
MAX_NOTEBOOK_LIST_ITEMS = 20
MAX_NOTEBOOK_LIST_ITEM_LENGTH = 300
MAX_NOTEBOOK_UUID_REFERENCES = 100


class NotebookReference(BaseModel):
    id: UUID
    type: Literal["alert", "hypothesis", "report"]
    title: str
    status: str | None = None
    timestamp: datetime | None = None
    relation: str


class NotebookEntry(BaseModel):
    id: UUID
    kind: Literal["report", "learning_hypothesis", "research_hypothesis"]
    title: str
    summary: str
    body: str
    status: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    folder: str
    tags: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    references: list[NotebookReference] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None


class NotebookFolder(BaseModel):
    name: str
    count: int


class NotebookSnapshot(BaseModel):
    generated_at: datetime
    source: Literal["database"]
    notes: list[NotebookEntry]
    folders: list[NotebookFolder]
    reference_counts: dict[str, int]


@router.get("", response_model=NotebookSnapshot)
async def get_notebook_snapshot(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> NotebookSnapshot:
    return await load_notebook_snapshot(session, limit=limit)


async def load_notebook_snapshot(session: AsyncSession, *, limit: int = 100) -> NotebookSnapshot:
    report_rows = (
        await session.scalars(
            select(ResearchReport).order_by(ResearchReport.published_at.desc()).limit(limit)
        )
    ).all()
    learning_rows = (
        await session.scalars(
            select(LearningHypothesis).order_by(LearningHypothesis.created_at.desc()).limit(limit)
        )
    ).all()
    research_rows = (
        await session.scalars(
            select(ResearchHypothesis).order_by(ResearchHypothesis.created_at.desc()).limit(limit)
        )
    ).all()
    report_alerts = await load_report_alerts(session, report_rows)

    entries = [
        *(entry_from_report(row, report_alerts) for row in report_rows),
        *(entry_from_learning_hypothesis(row) for row in learning_rows),
        *(entry_from_research_hypothesis(row) for row in research_rows),
    ]
    entries.sort(key=entry_sort_timestamp, reverse=True)
    entries = entries[:limit]

    folder_counts = defaultdict(int)
    reference_counts = {"alerts": 0, "hypotheses": 0, "reports": 0}
    for entry in entries:
        folder_counts[entry.folder] += 1
        for reference in entry.references:
            if reference.type == "alert":
                reference_counts["alerts"] += 1
            elif reference.type == "hypothesis":
                reference_counts["hypotheses"] += 1
            elif reference.type == "report":
                reference_counts["reports"] += 1

    return NotebookSnapshot(
        generated_at=datetime.now(timezone.utc),
        source="database",
        notes=entries,
        folders=[
            NotebookFolder(name=name, count=count)
            for name, count in sorted(folder_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        reference_counts=reference_counts,
    )


async def load_report_alerts(
    session: AsyncSession,
    reports: list[ResearchReport],
) -> dict[UUID, list[Alert]]:
    report_ids = {row.id for row in reports}
    related_alert_ids = {
        alert_id
        for row in reports
        for alert_id in parse_uuid_list(row.related_alert_ids)
    }
    if not report_ids and not related_alert_ids:
        return {}

    statement = select(Alert).order_by(Alert.triggered_at.desc()).limit(500)
    conditions = []
    if related_alert_ids:
        conditions.append(Alert.id.in_(related_alert_ids))
    if report_ids:
        conditions.append(Alert.related_research_id.in_(report_ids))
    statement = statement.where(or_(*conditions))
    alerts = (await session.scalars(statement)).all()

    grouped: dict[UUID, list[Alert]] = {report_id: [] for report_id in report_ids}
    report_by_alert_id = {
        alert_id: report.id
        for report in reports
        for alert_id in parse_uuid_list(report.related_alert_ids)
    }
    for alert in alerts:
        attached_report_id = alert.related_research_id or report_by_alert_id.get(alert.id)
        if attached_report_id is not None:
            grouped.setdefault(attached_report_id, []).append(alert)
    return grouped


def entry_from_report(
    row: ResearchReport,
    report_alerts: dict[UUID, list[Alert]] | None = None,
) -> NotebookEntry:
    alerts = report_alerts.get(row.id, []) if report_alerts else []
    references = [
        NotebookReference(
            id=alert.id,
            type="alert",
            title=alert.title,
            status=alert.status,
            timestamp=alert.triggered_at,
            relation="related_alert",
        )
        for alert in dedupe_alerts(alerts)[:MAX_NOTEBOOK_REFERENCES_PER_ENTRY]
    ]
    return NotebookEntry(
        id=row.id,
        kind="report",
        title=row.title,
        summary=row.summary,
        body=row.body,
        status="published",
        folder=report_folder(row.type),
        tags=string_list([row.type, *(row.hypotheses or [])], max_items=MAX_NOTEBOOK_TAGS),
        symbols=[],
        references=references,
        created_at=row.published_at,
        updated_at=None,
    )


def entry_from_learning_hypothesis(row: LearningHypothesis) -> NotebookEntry:
    body_sections = [
        format_list_section("supporting_evidence", row.supporting_evidence),
        row.proposed_change or "",
        format_list_section("counterevidence", row.counterevidence),
    ]
    return NotebookEntry(
        id=row.id,
        kind="learning_hypothesis",
        title=row.hypothesis,
        summary=row.proposed_change or row.evidence_strength,
        body="\n\n".join(section for section in body_sections if section),
        status=row.status,
        confidence=row.confidence,
        folder="学习假设",
        tags=[row.status, row.evidence_strength],
        symbols=[],
        references=[],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def entry_from_research_hypothesis(row: ResearchHypothesis) -> NotebookEntry:
    return NotebookEntry(
        id=row.id,
        kind="research_hypothesis",
        title=row.title,
        summary=row.description,
        body=row.description,
        status=row.status,
        confidence=row.confidence,
        folder="研究假设",
        tags=[row.status],
        symbols=[],
        references=[],
        created_at=row.created_at,
        updated_at=None,
    )


def parse_uuid_list(
    values: list | None,
    *,
    max_items: int = MAX_NOTEBOOK_UUID_REFERENCES,
) -> list[UUID]:
    parsed = []
    for value in values or []:
        if len(parsed) >= max_items:
            break
        try:
            parsed.append(value if isinstance(value, UUID) else UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return parsed


def string_list(
    values: list | None,
    *,
    max_items: int = MAX_NOTEBOOK_LIST_ITEMS,
    max_length: int = MAX_NOTEBOOK_LIST_ITEM_LENGTH,
) -> list[str]:
    rows: list[str] = []
    for value in values or []:
        text = str(value).strip()
        if not text:
            continue
        rows.append(text[:max_length])
        if len(rows) >= max_items:
            break
    return rows


def format_list_section(label: str, values: list | None) -> str:
    rows = string_list(values)
    if not rows:
        return ""
    return f"{label}:\n" + "\n".join(f"- {row}" for row in rows)


def report_folder(report_type: str) -> str:
    labels = {
        "daily": "研究报告",
        "weekly": "研究报告",
        "monthly": "研究报告",
        "strategy": "策略研究",
        "postmortem": "交易复盘",
    }
    return labels.get(report_type, "研究报告")


def dedupe_alerts(alerts: list[Alert]) -> list[Alert]:
    seen: set[UUID] = set()
    rows = []
    for alert in alerts:
        if alert.id in seen:
            continue
        seen.add(alert.id)
        rows.append(alert)
    return rows


def entry_sort_timestamp(entry: NotebookEntry) -> datetime:
    return entry.updated_at or entry.created_at
