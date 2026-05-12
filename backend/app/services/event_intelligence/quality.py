from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from app.models.event_intelligence import EventImpactLink, EventIntelligenceItem
from app.schemas.event_intelligence import (
    EventImpactLinkQualityRead,
    EventIntelligenceQualityIssue,
    EventIntelligenceQualityRead,
    EventIntelligenceQualitySummary,
)

DECISION_GRADE_SCORE = 82
SHADOW_READY_SCORE = 70
MIN_LINK_SCORE = 60


def evaluate_event_intelligence_quality(
    event_item: EventIntelligenceItem,
    links: list[EventImpactLink],
) -> EventIntelligenceQualityRead:
    link_reports = [evaluate_impact_link_quality(link) for link in links]
    issues = _event_quality_issues(event_item, links, link_reports)
    score = _event_quality_score(event_item, link_reports)
    has_blocker = any(issue.severity == "blocker" for issue in issues)
    usable_links = [report for report in link_reports if report.passed_gate]

    if has_blocker:
        status = "blocked"
    elif (
        event_item.requires_manual_confirmation
        or event_item.status == "human_review"
        or score < SHADOW_READY_SCORE
    ):
        status = "review"
    elif (
        event_item.status == "confirmed"
        and score >= DECISION_GRADE_SCORE
        and usable_links
        and all(report.score >= MIN_LINK_SCORE for report in usable_links)
    ):
        status = "decision_grade"
    else:
        status = "shadow_ready"

    return EventIntelligenceQualityRead(
        event_id=event_item.id,
        score=score,
        status=status,
        passed_gate=status in {"shadow_ready", "decision_grade"},
        decision_grade=status == "decision_grade",
        issues=issues,
        link_reports=link_reports,
    )


def evaluate_impact_link_quality(link: EventImpactLink) -> EventImpactLinkQualityRead:
    issues = _link_quality_issues(link)
    score = _link_quality_score(link)
    has_blocker = any(issue.severity == "blocker" for issue in issues)
    if has_blocker:
        status = "blocked"
    elif score < MIN_LINK_SCORE or link.status == "human_review":
        status = "review"
    else:
        status = "passed"

    return EventImpactLinkQualityRead(
        id=link.id,
        symbol=link.symbol,
        mechanism=link.mechanism,
        score=score,
        status=status,
        passed_gate=status == "passed",
        issues=issues,
    )


def summarize_event_intelligence_quality(
    reports: list[EventIntelligenceQualityRead],
) -> EventIntelligenceQualitySummary:
    total = len(reports)
    return EventIntelligenceQualitySummary(
        generated_at=datetime.now(UTC),
        total=total,
        average_score=round(sum(report.score for report in reports) / max(total, 1)),
        blocked=sum(1 for report in reports if report.status == "blocked"),
        review=sum(1 for report in reports if report.status == "review"),
        shadow_ready=sum(1 for report in reports if report.status == "shadow_ready"),
        decision_grade=sum(1 for report in reports if report.status == "decision_grade"),
        reports=reports,
    )


def _event_quality_score(
    event_item: EventIntelligenceItem,
    link_reports: list[EventImpactLinkQualityRead],
) -> int:
    evidence_score = min(1.0, len(event_item.evidence or []) / 2)
    counter_score = min(1.0, len(event_item.counterevidence or []) / 1)
    scope_score = (
        (1 if event_item.symbols else 0)
        + (1 if event_item.mechanisms else 0)
        + (1 if event_item.regions else 0)
    ) / 3
    link_score = (
        sum(report.score for report in link_reports) / (100 * len(link_reports))
        if link_reports
        else 0
    )
    score = (
        event_item.confidence * 22
        + event_item.source_reliability * 18
        + event_item.freshness_score * 14
        + evidence_score * 16
        + counter_score * 8
        + scope_score * 10
        + link_score * 12
    )
    if event_item.status == "confirmed":
        score += 4
    if event_item.status == "rejected":
        score -= 30
    return _score(score)


def _link_quality_score(link: EventImpactLink) -> int:
    evidence_score = min(1.0, len(link.evidence or []) / 1)
    counter_score = min(1.0, len(link.counterevidence or []) / 1)
    rationale_score = 1.0 if (link.rationale or "").strip() else 0.0
    status_score = {
        "confirmed": 1.0,
        "shadow_review": 0.82,
        "human_review": 0.45,
        "rejected": 0.0,
    }.get(link.status, 0.55)
    score = (
        link.confidence * 34
        + min(1.0, link.impact_score / 100) * 22
        + evidence_score * 20
        + counter_score * 8
        + rationale_score * 8
        + status_score * 8
    )
    return _score(score)


def _event_quality_issues(
    event_item: EventIntelligenceItem,
    links: list[EventImpactLink],
    link_reports: list[EventImpactLinkQualityRead],
) -> list[EventIntelligenceQualityIssue]:
    issues: list[EventIntelligenceQualityIssue] = []
    if event_item.status == "rejected":
        issues.append(_issue("event_rejected", "blocker", "事件已被拒绝，不能进入后续链路。"))
    if not event_item.symbols:
        issues.append(_issue("missing_symbols", "blocker", "事件缺少影响品种。"))
    if not event_item.mechanisms:
        issues.append(_issue("missing_mechanisms", "blocker", "事件缺少影响机制。"))
    if not event_item.evidence:
        issues.append(_issue("missing_evidence", "blocker", "事件缺少支持证据。"))
    if not links:
        issues.append(_issue("missing_impact_links", "blocker", "事件暂无商品影响链。"))
    if links and all(report.status == "blocked" for report in link_reports):
        issues.append(_issue("no_usable_impact_links", "blocker", "事件影响链全部未通过质量门。"))
    elif links and not any(report.passed_gate for report in link_reports):
        issues.append(_issue("impact_links_need_review", "warning", "事件影响链需要复核后才能升级。"))
    if event_item.requires_manual_confirmation or event_item.status == "human_review":
        issues.append(_issue("manual_review_required", "warning", "事件需要人工复核后才能升级。"))
    if event_item.confidence < 0.55:
        issues.append(_issue("low_confidence", "warning", "事件置信度偏低。"))
    if event_item.source_reliability < 0.5:
        issues.append(_issue("weak_source", "warning", "事件来源可信度偏低。"))
    if event_item.freshness_score < 0.5:
        issues.append(_issue("stale_event", "warning", "事件新鲜度不足。"))
    if event_item.impact_score >= 70 and not event_item.counterevidence:
        issues.append(_issue("missing_counterevidence", "warning", "高影响事件缺少反证线索。"))
    return issues


def _link_quality_issues(link: EventImpactLink) -> list[EventIntelligenceQualityIssue]:
    issues: list[EventIntelligenceQualityIssue] = []
    if link.status == "rejected":
        issues.append(_issue("link_rejected", "blocker", "影响链已被拒绝。"))
    if not link.symbol:
        issues.append(_issue("link_missing_symbol", "blocker", "影响链缺少品种。"))
    if not link.mechanism:
        issues.append(_issue("link_missing_mechanism", "blocker", "影响链缺少机制。"))
    if not link.evidence:
        issues.append(_issue("link_missing_evidence", "blocker", "影响链缺少支持证据。"))
    if link.confidence < 0.45:
        issues.append(_issue("link_low_confidence", "warning", "影响链置信度偏低。"))
    if link.direction == "watch":
        issues.append(_issue("link_watch_only", "info", "影响链当前仅建议观察。"))
    if not (link.rationale or "").strip():
        issues.append(_issue("link_missing_rationale", "warning", "影响链缺少机制说明。"))
    return issues


def _issue(
    code: str,
    severity: Literal["blocker", "warning", "info"],
    message: str,
) -> EventIntelligenceQualityIssue:
    return EventIntelligenceQualityIssue(
        code=code,
        severity=severity,
        message=message,
    )


def _score(value: float) -> int:
    return round(max(0, min(100, value)))
