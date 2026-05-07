from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import create_app
from app.models.llm_cache import LLMCache, LLMBudget
from app.services.llm.budget_guard import add_budget_spend, month_bounds
from app.services.llm.cache import get_cached_completion, llm_cache_key, store_cached_completion
from app.services.llm.cost_tracker import LLMUsageSummary, estimate_cost_usd, record_llm_usage
from app.services.llm.types import LLMCompletionResult, LLMUsage


class FakeScalars:
    def __init__(self, row=None) -> None:
        self.row = row

    def first(self):
        return self.row


class FakeSession:
    def __init__(self, row=None, *, fail_scalars: bool = False, fail_flush: bool = False) -> None:
        self.row = row
        self.fail_scalars = fail_scalars
        self.fail_flush = fail_flush
        self.added: list[object] = []
        self.scalars_count = 0
        self.flush_count = 0
        self.rollback_count = 0

    async def scalars(self, _statement):
        self.scalars_count += 1
        if self.fail_scalars:
            raise RuntimeError("lookup failed")
        return FakeScalars(self.row)

    def add(self, row: object) -> None:
        self.added.append(row)
        self.row = row

    async def flush(self) -> None:
        self.flush_count += 1
        if self.fail_flush:
            raise RuntimeError("flush failed")

    async def rollback(self) -> None:
        self.rollback_count += 1


def test_llm_cache_key_is_stable_and_provider_scoped() -> None:
    left = llm_cache_key(provider="openai", model="m1", system="s", user="u")
    right = llm_cache_key(provider="openai", model="m1", system="s", user="u")
    other = llm_cache_key(provider="deepseek", model="m1", system="s", user="u")

    assert left == right
    assert left != other


def test_llm_cache_key_includes_output_constraints() -> None:
    base = llm_cache_key(provider="openai", model="m1", system="s", user="u")
    json_mode = llm_cache_key(
        provider="openai",
        model="m1",
        system="s",
        user="u",
        json_mode=True,
    )
    limited = llm_cache_key(
        provider="openai",
        model="m1",
        system="s",
        user="u",
        max_tokens=200,
    )
    cool = llm_cache_key(
        provider="openai",
        model="m1",
        system="s",
        user="u",
        temperature=0,
    )

    assert len({base, json_mode, limited, cool}) == 4


def test_llm_cache_key_canonicalizes_json_schema() -> None:
    left = llm_cache_key(
        provider="openai",
        model="m1",
        system="s",
        user="u",
        json_mode=True,
        json_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
    )
    right = llm_cache_key(
        provider="openai",
        model="m1",
        system="s",
        user="u",
        json_mode=True,
        json_schema={"properties": {"ok": {"type": "boolean"}}, "type": "object"},
    )

    assert left == right


async def test_store_cached_completion_updates_existing_cache_row() -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    existing = LLMCache(
        cache_key="cache-key",
        module="old",
        provider="openai",
        model="old-model",
        system_hash="old",
        user_hash="old",
        response={"content": "old"},
        hit_count=4,
        expires_at=now,
    )
    session = FakeSession(existing)
    result = LLMCompletionResult(
        content="fresh",
        model="grok-4.3",
        usage=LLMUsage(input_tokens=10, output_tokens=4),
        raw={"id": "resp-1"},
    )

    row = await store_cached_completion(
        session,  # type: ignore[arg-type]
        cache_key="cache-key",
        module="news",
        provider="xai",
        model="grok-4.3",
        system="system",
        user="user",
        result=result,
        ttl=timedelta(minutes=30),
        as_of=now,
    )

    assert row is existing
    assert session.added == []
    assert session.scalars_count == 1
    assert session.flush_count == 1
    assert existing.module == "news"
    assert existing.provider == "xai"
    assert existing.response["content"] == "fresh"
    assert existing.response["usage"] == {"input_tokens": 10, "output_tokens": 4}
    assert existing.hit_count == 0
    assert existing.expires_at == now + timedelta(minutes=30)


async def test_get_cached_completion_returns_cached_payload_when_hit_update_fails() -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    row = LLMCache(
        cache_key="cache-key",
        module="news",
        provider="xai",
        model="grok-4.3",
        system_hash="system",
        user_hash="user",
        response={
            "content": "cached",
            "model": "grok-4.3",
            "usage": {"input_tokens": 9, "output_tokens": 3},
            "raw": {"id": "cached-1"},
        },
        hit_count=7,
        expires_at=now + timedelta(hours=1),
    )
    session = FakeSession(row, fail_flush=True)

    result = await get_cached_completion(
        session,  # type: ignore[arg-type]
        cache_key="cache-key",
        as_of=now,
    )

    assert result is not None
    assert result.content == "cached"
    assert result.model == "grok-4.3"
    assert result.usage is not None
    assert result.usage.input_tokens == 9
    assert session.flush_count == 1
    assert session.rollback_count == 1


async def test_store_cached_completion_rolls_back_lookup_failure() -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    session = FakeSession(fail_scalars=True)

    row = await store_cached_completion(
        session,  # type: ignore[arg-type]
        cache_key="cache-key",
        module="news",
        provider="xai",
        model="grok-4.3",
        system="system",
        user="user",
        result=LLMCompletionResult(content="fresh", model="grok-4.3"),
        as_of=now,
    )

    assert row is None
    assert session.rollback_count == 1
    assert session.flush_count == 0


async def test_record_llm_usage_rolls_back_flush_failure() -> None:
    session = FakeSession(fail_flush=True)

    row = await record_llm_usage(
        session,  # type: ignore[arg-type]
        module="alert_agent",
        provider="xai",
        model="grok-4.3",
        input_tokens=10,
        output_tokens=4,
    )

    assert row is None
    assert session.flush_count == 1
    assert session.rollback_count == 1


async def test_add_budget_spend_rolls_back_flush_failure() -> None:
    now = datetime(2026, 5, 5, tzinfo=timezone.utc)
    budget = LLMBudget(
        module="alert_agent",
        monthly_budget_usd=10.0,
        current_spend_usd=1.0,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 6, 1),
        status="active",
    )
    session = FakeSession(budget, fail_flush=True)

    await add_budget_spend(
        session,  # type: ignore[arg-type]
        module="alert_agent",
        amount_usd=0.25,
        as_of=now,
    )

    assert session.scalars_count == 1
    assert session.flush_count == 1
    assert session.rollback_count == 1


def test_month_bounds_returns_next_month_exclusive_end() -> None:
    assert month_bounds(date(2026, 5, 3)) == (date(2026, 5, 1), date(2026, 6, 1))
    assert month_bounds(date(2026, 12, 3)) == (date(2026, 12, 1), date(2027, 1, 1))


def test_cost_estimate_is_zero_for_unknown_usage() -> None:
    assert estimate_cost_usd("gpt-test", 0, 0) == 0.0
    assert estimate_cost_usd("gpt-test", 1000, 1000) > 0


def test_llm_usage_api_returns_requested_month_summary(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_db():
        yield object()

    async def fake_monthly_usage_summary(
        session,
        *,
        module: str,
        period_start: date,
        period_end: date,
    ) -> LLMUsageSummary:
        captured.update(
            {
                "session": session,
                "module": module,
                "period_start": period_start,
                "period_end": period_end,
            }
        )
        return LLMUsageSummary(
            module=module,
            period_start=period_start,
            period_end=period_end,
            calls=7,
            cache_hits=3,
            estimated_cost_usd=1.2345,
            input_tokens=1200,
            output_tokens=450,
        )

    monkeypatch.setattr(
        "app.api.llm_usage.monthly_usage_summary",
        fake_monthly_usage_summary,
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.get("/api/llm/usage?module=news&month=2026-05-16")

    assert response.status_code == 200
    assert captured["module"] == "news"
    assert captured["period_start"] == date(2026, 5, 1)
    assert captured["period_end"] == date(2026, 6, 1)
    assert response.json() == {
        "module": "news",
        "period_start": "2026-05-01",
        "period_end": "2026-06-01",
        "calls": 7,
        "cache_hits": 3,
        "estimated_cost_usd": 1.2345,
        "input_tokens": 1200,
        "output_tokens": 450,
    }
