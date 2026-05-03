from datetime import datetime, timezone

from app.services.news.dedup import news_dedup_hash, normalize_title
from app.models.news_events import NewsEvent
from app.services.news.event_publisher import event_row_is_evaluable, jsonable_news_payload, upsert_news_event
from app.services.news.extractor import extract_news_event_sync
from app.services.news.quality import is_evaluable_news_event, requires_manual_confirmation
from app.services.news.types import RawNewsItem


class FakeScalars:
    def __init__(self, row=None) -> None:
        self._row = row

    def first(self):
        return self._row


class FakeSession:
    def __init__(self) -> None:
        self.rows: list[object] = []
        self.flush_count = 0

    async def scalars(self, _):
        return FakeScalars()

    def add(self, row: object) -> None:
        self.rows.append(row)

    async def flush(self) -> None:
        self.flush_count += 1


def test_news_extractor_maps_commodity_event_fields() -> None:
    item = RawNewsItem(
        source="cailianshe",
        title="OPEC+ 宣布延长减产",
        content_text="OPEC+ 延长自愿减产安排，原油供应下降，SC 原油短线偏多。",
        published_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
    )

    event = extract_news_event_sync(item)

    assert event.event_type == "supply"
    assert event.direction == "bullish"
    assert event.severity == 5
    assert "SC" in event.affected_symbols
    assert event.dedup_hash is not None


def test_news_title_hash_normalizes_punctuation() -> None:
    published_at = datetime(2026, 5, 3, tzinfo=timezone.utc)

    left = news_dedup_hash(
        title="OPEC+ 宣布延长减产！",
        published_at=published_at,
        affected_symbols=["SC"],
    )
    right = news_dedup_hash(
        title="opec 宣布延长减产",
        published_at=published_at,
        affected_symbols=["SC"],
    )

    assert normalize_title("OPEC+ 宣布延长减产！") == "opec宣布延长减产"
    assert left == right


def test_news_quality_gate_requires_confirmation_for_single_source_severe_event() -> None:
    assert requires_manual_confirmation(
        severity=4,
        source_count=1,
        verification_status="single_source",
    )
    assert not is_evaluable_news_event(
        severity=4,
        source_count=1,
        verification_status="single_source",
    )
    assert is_evaluable_news_event(
        severity=4,
        source_count=2,
        verification_status="cross_verified",
    )


def test_duplicate_payload_is_json_safe() -> None:
    payload = {
        "published_at": datetime(2026, 5, 3, tzinfo=timezone.utc),
        "nested": {"symbols": ["SC"]},
    }

    converted = jsonable_news_payload(payload)

    assert converted["published_at"] == "2026-05-03T00:00:00+00:00"
    assert converted["nested"] == {"symbols": ["SC"]}


def test_news_event_publish_gate_detects_evaluable_transition() -> None:
    row = NewsEvent(
        source="exchange_announcements",
        title="交易所提示铁矿石合约交易风险",
        summary="单源事件等待确认。",
        published_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        event_type="policy",
        affected_symbols=["I"],
        direction="mixed",
        severity=4,
        time_horizon="immediate",
        llm_confidence=0.68,
        source_count=1,
        verification_status="single_source",
        requires_manual_confirmation=True,
        dedup_hash="hash",
    )

    assert not event_row_is_evaluable(row)
    row.source_count = 2
    row.verification_status = "cross_verified"
    row.requires_manual_confirmation = False

    assert event_row_is_evaluable(row)


async def test_new_manual_confirmation_event_is_not_published() -> None:
    session = FakeSession()

    row, created, should_publish = await upsert_news_event(  # type: ignore[arg-type]
        session,
        {
            "source": "exchange_announcements",
            "title": "交易所提示铁矿石合约交易风险",
            "summary": "单源事件等待确认。",
            "published_at": datetime(2026, 5, 3, tzinfo=timezone.utc),
            "event_type": "policy",
            "affected_symbols": ["I"],
            "direction": "mixed",
            "severity": 4,
            "time_horizon": "immediate",
            "llm_confidence": 0.68,
            "source_count": 1,
            "verification_status": "single_source",
        },
    )

    assert created is True
    assert row.requires_manual_confirmation is True
    assert should_publish is False
