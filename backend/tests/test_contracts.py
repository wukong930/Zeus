from datetime import date, datetime, timezone

from app.models.market_data import MarketData
from app.services.contracts.main_contract_batch import (
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
