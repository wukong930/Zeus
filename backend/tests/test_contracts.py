from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.dialects import postgresql

from app.models.market_data import MarketData
from app.services.contracts.main_contract_batch import (
    _contract_metadata_by_symbol_month_statement,
    _current_main_contract_statement,
    contract_candidate_from_market_data,
    latest_contract_snapshots,
)
from app.services.contracts.continuous import PricePoint, build_back_adjusted_main_series
from app.services.contracts.main_contract_detector import (
    ContractCandidate,
    detect_main_contract_switch,
)


def test_detect_main_contract_switch_requires_three_confirming_days() -> None:
    candidates = [
        ContractCandidate("RB", "2405", date(2026, 5, 1), 100, 100),
        ContractCandidate("RB", "2410", date(2026, 5, 1), 90, 90),
        ContractCandidate("RB", "2405", date(2026, 5, 2), 100, 100),
        ContractCandidate("RB", "2410", date(2026, 5, 2), 120, 120),
        ContractCandidate("RB", "2405", date(2026, 5, 3), 100, 100),
        ContractCandidate("RB", "2410", date(2026, 5, 3), 130, 130),
    ]

    assert detect_main_contract_switch(candidates, current_contract_month="2405") is None

    candidates.append(ContractCandidate("RB", "2410", date(2026, 5, 4), 140, 140))
    candidates.append(ContractCandidate("RB", "2405", date(2026, 5, 4), 100, 100))

    switch = detect_main_contract_switch(candidates, current_contract_month="2405")

    assert switch is not None
    assert switch.contract_month == "2410"


def test_build_back_adjusted_main_series_removes_roll_gap() -> None:
    points = [
        PricePoint(datetime(2026, 5, 1, tzinfo=timezone.utc), "2405", 100),
        PricePoint(datetime(2026, 5, 2, tzinfo=timezone.utc), "2405", 102),
        PricePoint(datetime(2026, 5, 3, tzinfo=timezone.utc), "2410", 96),
    ]

    continuous = build_back_adjusted_main_series(points)

    assert continuous[-1].raw_close == 96
    assert continuous[-1].adjusted_close == 102
    assert continuous[-1].adjustment == 6


def _market_row(contract_month: str, timestamp: datetime, volume: float) -> MarketData:
    return MarketData(
        market="CN",
        exchange="SHFE",
        commodity="rebar",
        symbol="RB",
        contract_month=contract_month,
        timestamp=timestamp,
        open=100,
        high=101,
        low=99,
        close=100,
        volume=volume,
        open_interest=volume * 2,
    )


def test_contract_candidate_from_market_data_preserves_liquidity_inputs() -> None:
    timestamp = datetime(2026, 5, 3, tzinfo=timezone.utc)
    row = _market_row("2601", timestamp, 1000)

    candidate = contract_candidate_from_market_data(row)

    assert candidate == ContractCandidate("RB", "2601", timestamp.date(), 1000, 2000)


def test_latest_contract_snapshots_keeps_latest_row_per_month() -> None:
    older = _market_row("2601", datetime(2026, 5, 1, tzinfo=timezone.utc), 100)
    newer = _market_row("2601", datetime(2026, 5, 2, tzinfo=timezone.utc), 200)
    other = _market_row("2605", datetime(2026, 5, 1, tzinfo=timezone.utc), 300)

    snapshots = latest_contract_snapshots([newer, other, older])

    assert snapshots["2601"] is newer
    assert snapshots["2605"] is other


def test_latest_contract_snapshots_breaks_same_timestamp_ties_by_revision() -> None:
    timestamp = datetime(2026, 5, 2, tzinfo=timezone.utc)
    vintage = datetime(2026, 5, 2, 9, tzinfo=timezone.utc)
    older_revision = _market_row("2601", timestamp, 100)
    older_revision.vintage_at = vintage
    older_revision.ingested_at = vintage
    older_revision.id = UUID("00000000-0000-0000-0000-000000000001")
    newer_revision = _market_row("2601", timestamp, 200)
    newer_revision.vintage_at = vintage
    newer_revision.ingested_at = vintage
    newer_revision.id = UUID("00000000-0000-0000-0000-000000000002")

    snapshots = latest_contract_snapshots([newer_revision, older_revision])

    assert snapshots["2601"] is newer_revision


def test_current_main_contract_statement_uses_stable_latest_order() -> None:
    sql = _compile_postgres(_current_main_contract_statement(symbol="RB"))

    assert "contract_metadata.symbol = 'RB'" in sql
    assert "contract_metadata.is_main IS true" in sql
    assert "contract_metadata.main_until IS NULL" in sql
    assert (
        "ORDER BY contract_metadata.main_from DESC NULLS LAST, "
        "contract_metadata.updated_at DESC, contract_metadata.id DESC"
    ) in sql
    assert "LIMIT 1" in sql


def test_contract_metadata_by_symbol_month_statement_uses_stable_order() -> None:
    sql = _compile_postgres(
        _contract_metadata_by_symbol_month_statement(symbol="RB", contract_month="2601")
    )

    assert "contract_metadata.symbol = 'RB'" in sql
    assert "contract_metadata.contract_month = '2601'" in sql
    assert "ORDER BY contract_metadata.updated_at DESC, contract_metadata.id DESC" in sql
    assert "LIMIT 1" in sql


def _compile_postgres(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
