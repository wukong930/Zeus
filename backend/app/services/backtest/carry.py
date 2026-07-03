"""Term-structure carry factor from per-contract data.

Carry (roll yield) is the classic, well-documented commodity factor that the
reversal-only signal set lacks. For each commodity on each day it is the
annualized log slope between the two nearest-maturity liquid contracts:
backwardation (front > next) => positive carry (you earn the roll); contango =>
negative. Cross-sectionally, long high-carry / short low-carry.
"""

from __future__ import annotations

import math
import re


def contract_maturity(contract: str) -> tuple[int, int] | None:
    """Parse the trailing YYMM of a contract code (e.g. 'rb2410' -> (2024, 10))."""

    match = re.search(r"(\d{4})\b", contract.strip())
    if not match:
        match = re.search(r"(\d{4})$", contract.strip())
    if not match:
        return None
    yymm = match.group(1)
    year, month = 2000 + int(yymm[:2]), int(yymm[2:])
    if not 1 <= month <= 12:
        return None
    return year, month


def _month_index(maturity: tuple[int, int]) -> int:
    return maturity[0] * 12 + maturity[1]


def carry_signal(contracts: dict[str, tuple[float, float]], *, min_oi: float = 0.0) -> float | None:
    """Annualized roll yield between the two nearest liquid contracts.

    ``contracts`` maps contract code -> (close, open_interest) for one commodity
    on one day. Returns None if fewer than two liquid, dated contracts exist.
    """

    points: list[tuple[int, float]] = []
    for code, (close, open_interest) in contracts.items():
        maturity = contract_maturity(code)
        if maturity is not None and close > 0 and open_interest >= min_oi:
            points.append((_month_index(maturity), close))
    if len({mi for mi, _ in points}) < 2:
        return None
    points.sort()
    (front_index, front_close), (next_index, next_close) = points[0], points[1]
    if next_close <= 0:
        return None
    gap_months = max(1, next_index - front_index)
    return math.log(front_close / next_close) / gap_months * 12
