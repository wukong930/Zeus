from __future__ import annotations

from dataclasses import dataclass
from datetime import date

DEFAULT_TRAINING_YEARS = 3
DEFAULT_TEST_MONTHS = 3
DEFAULT_STEP_MONTHS = 1


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    train_start: date
    train_end: date
    test_start: date
    test_end: date

    def to_dict(self) -> dict:
        return {
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat(),
        }


def walk_forward_defaults() -> dict:
    return {
        "training_years": DEFAULT_TRAINING_YEARS,
        "test_months": DEFAULT_TEST_MONTHS,
        "step_months": DEFAULT_STEP_MONTHS,
        "mode": "rolling",
    }


def generate_walk_forward_windows(
    *,
    start: date,
    end: date,
    training_years: int = DEFAULT_TRAINING_YEARS,
    test_months: int = DEFAULT_TEST_MONTHS,
    step_months: int = DEFAULT_STEP_MONTHS,
) -> list[WalkForwardWindow]:
    windows: list[WalkForwardWindow] = []
    train_start = start
    while True:
        train_end = _add_months(train_start, training_years * 12)
        test_start = train_end
        test_end = _add_months(test_start, test_months)
        if test_end > end:
            break
        windows.append(
            WalkForwardWindow(
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
        )
        train_start = _add_months(train_start, step_months)
    return windows


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 2:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        return 29 if leap else 28
    if month in {4, 6, 9, 11}:
        return 30
    return 31
