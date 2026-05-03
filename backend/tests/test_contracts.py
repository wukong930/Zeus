from datetime import date, datetime, timezone

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
