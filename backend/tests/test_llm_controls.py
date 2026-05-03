from datetime import date

from app.services.llm.budget_guard import month_bounds
from app.services.llm.cache import llm_cache_key
from app.services.llm.cost_tracker import estimate_cost_usd


def test_llm_cache_key_is_stable_and_provider_scoped() -> None:
    left = llm_cache_key(provider="openai", model="m1", system="s", user="u")
    right = llm_cache_key(provider="openai", model="m1", system="s", user="u")
    other = llm_cache_key(provider="deepseek", model="m1", system="s", user="u")

    assert left == right
    assert left != other


def test_month_bounds_returns_next_month_exclusive_end() -> None:
    assert month_bounds(date(2026, 5, 3)) == (date(2026, 5, 1), date(2026, 6, 1))
    assert month_bounds(date(2026, 12, 3)) == (date(2026, 12, 1), date(2027, 1, 1))


def test_cost_estimate_is_zero_for_unknown_usage() -> None:
    assert estimate_cost_usd("gpt-test", 0, 0) == 0.0
    assert estimate_cost_usd("gpt-test", 1000, 1000) > 0
