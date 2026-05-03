from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.position import Position
from app.models.recommendation import Recommendation
from app.services.learning.recommendation_attribution import (
    calculate_position_pnl,
    update_recommendation_from_position,
)
from app.services.pipeline.handlers import position_conflict_warnings
from app.services.positions.data_freshness import check_position_freshness
from app.services.positions.propagation_activator import infer_category_from_symbol
from app.services.positions.threshold_modifier import (
    get_position_aware_thresholds,
    get_position_threshold_multiplier,
    refresh_position_threshold_cache,
    update_position_threshold_cache,
)
from app.services.scoring.portfolio_fit import PositionGroup, RecommendationLeg


class FakeScalars:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, *, recommendation=None, rows=None) -> None:
        self.recommendation = recommendation
        self.rows = rows or []
        self.flush_count = 0

    async def get(self, _, __):
        return self.recommendation

    async def scalars(self, _):
        return FakeScalars(self.rows)

    async def flush(self) -> None:
        self.flush_count += 1


def _position(**overrides) -> Position:
    values = {
        "id": uuid4(),
        "strategy_name": "phase6",
        "legs": [{"asset": "RU", "direction": "long", "lots": 2, "contract_multiplier": 10}],
        "opened_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
        "entry_spread": 100,
        "current_spread": 108,
        "spread_unit": "price",
        "unrealized_pnl": 0,
        "total_margin_used": 10_000,
        "exit_condition": "manual_close",
        "target_z_score": 0,
        "current_z_score": 0,
        "half_life_days": 0,
        "days_held": 0,
        "status": "open",
        "manual_entry": True,
        "avg_entry_price": 100,
        "monitoring_priority": 5,
        "propagation_nodes": [],
        "last_updated_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
        "data_mode": "position_aware",
    }
    values.update(overrides)
    return Position(**values)


def _recommendation(recommendation_id) -> Recommendation:
    return Recommendation(
        id=recommendation_id,
        status="pending",
        recommended_action="open_spread",
        legs=[{"asset": "RU", "direction": "long"}],
        priority_score=80,
        portfolio_fit_score=70,
        margin_efficiency_score=80,
        margin_required=10_000,
        reasoning="phase6 attribution",
        risk_items=[],
        expires_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        entry_price=100,
    )


def test_position_threshold_cache_lowers_held_symbol_thresholds() -> None:
    position = _position()

    update_position_threshold_cache(position)
    thresholds = get_position_aware_thresholds("rubber", symbols=("RU",))

    assert get_position_threshold_multiplier(("RU",)) == 0.8
    assert thresholds.z_score_entry < get_position_aware_thresholds("rubber", symbols=("CU",)).z_score_entry

    update_position_threshold_cache(_position(id=position.id, status="closed"))


async def test_refresh_position_threshold_cache_hydrates_existing_open_positions() -> None:
    position = _position()
    session = FakeSession(rows=[position])

    await refresh_position_threshold_cache(session)  # type: ignore[arg-type]

    assert get_position_threshold_multiplier(("RU",)) == 0.8

    await refresh_position_threshold_cache(FakeSession(rows=[]))  # type: ignore[arg-type]
    assert get_position_threshold_multiplier(("RU",)) == 1.0


def test_position_conflict_warning_marks_reverse_signal() -> None:
    warnings = position_conflict_warnings(
        [RecommendationLeg(asset="RU", direction="short")],
        [PositionGroup(legs=[RecommendationLeg(asset="RU", direction="long")])],
    )

    assert warnings == ["Position conflict: RU signal is short, open position is long."]


async def test_recommendation_attribution_updates_closed_trade() -> None:
    recommendation_id = uuid4()
    recommendation = _recommendation(recommendation_id)
    position = _position(
        recommendation_id=recommendation_id,
        status="closed",
        current_spread=108,
        closed_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
    )
    session = FakeSession(recommendation=recommendation)

    result = await update_recommendation_from_position(session, position)  # type: ignore[arg-type]

    assert result.updated is True
    assert recommendation.status == "completed"
    assert recommendation.pnl_realized == 160
    assert recommendation.holding_period_days == 2
    assert recommendation.mfe == 8


def test_calculate_position_pnl_respects_short_direction() -> None:
    position = _position(legs=[{"asset": "RU", "direction": "short", "lots": 1}])

    assert calculate_position_pnl(position, actual_entry=100, actual_exit=92) == 8


async def test_position_freshness_marks_stale_and_degrades_old_positions() -> None:
    as_of = datetime(2026, 5, 20, tzinfo=timezone.utc)
    position = _position(last_updated_at=as_of - timedelta(days=16))
    session = FakeSession(rows=[position])
    update_position_threshold_cache(position)

    result = await check_position_freshness(session, as_of=as_of)  # type: ignore[arg-type]

    assert result.stale == 1
    assert result.degraded == 1
    assert position.data_mode == "stale_no_position"
    assert get_position_threshold_multiplier(("RU",)) == 1.0


def test_phase6_symbol_category_fallback_covers_rubber() -> None:
    assert infer_category_from_symbol("RU") == "rubber"
