from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.alert import Alert
from app.models.news_events import NewsEvent
from app.services.translation.market import GLOSSARY_VERSION
from app.services.translation.market import translate_market_text_pair_with_llm


@dataclass(frozen=True)
class TranslationBackfillResult:
    news_scanned: int
    news_updated: int
    alerts_scanned: int
    alerts_updated: int
    llm_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "completed",
            "news_scanned": self.news_scanned,
            "news_updated": self.news_updated,
            "alerts_scanned": self.alerts_scanned,
            "alerts_updated": self.alerts_updated,
            "llm_enabled": self.llm_enabled,
        }


async def backfill_translations(
    session: AsyncSession,
    *,
    limit: int | None = None,
    use_llm: bool | None = None,
) -> TranslationBackfillResult:
    settings = get_settings()
    active_limit = limit or settings.translation_backfill_limit
    llm_enabled = settings.translation_llm_enabled if use_llm is None else use_llm
    news_rows = list(
        (
            await session.scalars(
                select(NewsEvent)
                .where(
                    or_(
                        NewsEvent.title_zh.is_(None),
                        NewsEvent.summary_zh.is_(None),
                        NewsEvent.translation_status.in_(("pending", "failed")),
                        NewsEvent.translation_glossary_version != GLOSSARY_VERSION,
                    )
                )
                .order_by(NewsEvent.published_at.desc())
                .limit(active_limit)
            )
        ).all()
    )
    alert_rows = list(
        (
            await session.scalars(
                select(Alert)
                .where(
                    or_(
                        Alert.title_zh.is_(None),
                        Alert.summary_zh.is_(None),
                        Alert.translation_status.in_(("pending", "failed")),
                        Alert.translation_glossary_version != GLOSSARY_VERSION,
                    )
                )
                .order_by(Alert.triggered_at.desc())
                .limit(active_limit)
            )
        ).all()
    )

    news_updated = 0
    for row in news_rows:
        translated = await translate_market_text_pair_with_llm(
            session,
            title=row.title,
            summary=row.summary,
            use_llm=llm_enabled,
        )
        _apply_translation(row, translated.to_model_fields())
        news_updated += 1

    alerts_updated = 0
    for row in alert_rows:
        translated = await translate_market_text_pair_with_llm(
            session,
            title=row.title_original or row.title,
            summary=row.summary_original or row.summary,
            use_llm=llm_enabled,
        )
        _apply_translation(row, translated.to_model_fields())
        alerts_updated += 1

    await session.flush()
    return TranslationBackfillResult(
        news_scanned=len(news_rows),
        news_updated=news_updated,
        alerts_scanned=len(alert_rows),
        alerts_updated=alerts_updated,
        llm_enabled=llm_enabled,
    )


def _apply_translation(row: NewsEvent | Alert, fields: dict[str, Any]) -> None:
    row.title_original = fields.get("title_original")
    row.summary_original = fields.get("summary_original")
    row.title_zh = fields.get("title_zh")
    row.summary_zh = fields.get("summary_zh")
    row.source_language = str(fields.get("source_language") or "unknown")
    row.translation_status = str(fields.get("translation_status") or "pending")
    row.translation_model = fields.get("translation_model")
    row.translation_prompt_version = fields.get("translation_prompt_version")
    row.translation_glossary_version = fields.get("translation_glossary_version")
    row.translated_at = fields.get("translated_at")
