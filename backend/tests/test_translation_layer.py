from datetime import datetime, timezone

from app.models.alert import Alert
from app.models.news_events import NewsEvent
from app.services.translation.backfill import backfill_translations
from app.services.translation.market import (
    detect_language,
    translate_market_text_pair,
)


class FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, news_rows=None, alert_rows=None) -> None:
        self.news_rows = news_rows or []
        self.alert_rows = alert_rows or []
        self.calls = 0
        self.flush_count = 0

    async def scalars(self, _statement):
        self.calls += 1
        return FakeScalars(self.news_rows if self.calls == 1 else self.alert_rows)

    async def flush(self) -> None:
        self.flush_count += 1


def test_market_translation_uses_commodity_glossary() -> None:
    result = translate_market_text_pair(
        "Thailand floods disrupt natural rubber tapping",
        "Heavy rainfall in southern Thailand disrupts rubber tapping and exports.",
    )

    assert result.source_language == "en"
    assert result.translation_status == "glossary"
    assert "泰国" in result.title_zh
    assert "天然橡胶" in result.title_zh
    assert "降雨" in result.summary_zh


def test_market_translation_keeps_chinese_source() -> None:
    result = translate_market_text_pair("OPEC+ 宣布延长减产", "原油供应下降，SC 原油短线偏多。")

    assert detect_language(result.title_zh) == "zh"
    assert result.translation_status == "source_zh"
    assert result.title_original == result.title_zh


async def test_translation_backfill_updates_news_and_alert_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.translation.backfill.get_settings",
        lambda: type("Settings", (), {"translation_backfill_limit": 10, "translation_llm_enabled": False})(),
    )
    news = NewsEvent(
        source="gdelt",
        title="Thailand floods disrupt natural rubber tapping",
        summary="Heavy rainfall disrupts rubber tapping.",
        published_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        event_type="weather",
        affected_symbols=["RU", "NR"],
        direction="bullish",
        severity=4,
        time_horizon="short",
        llm_confidence=0.8,
        source_count=2,
        verification_status="cross_verified",
        requires_manual_confirmation=False,
        dedup_hash="hash",
    )
    alert = Alert(
        title="SC supply news event",
        summary="OPEC+ extends production cuts, bullish for crude oil.",
        severity="high",
        category="energy",
        type="news_event",
        triggered_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        confidence=0.8,
        related_assets=["SC"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )
    session = FakeSession(news_rows=[news], alert_rows=[alert])

    result = await backfill_translations(session, use_llm=False)  # type: ignore[arg-type]

    assert result.news_updated == 1
    assert result.alerts_updated == 1
    assert "天然橡胶" in (news.title_zh or "")
    assert "原油" in (alert.summary_zh or "")
    assert session.flush_count == 1
