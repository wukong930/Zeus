from collections import defaultdict
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ContractCandidate:
    symbol: str
    contract_month: str
    trading_date: date
    volume: float
    open_interest: float

    @property
    def liquidity_score(self) -> float:
        return self.volume + self.open_interest


def daily_leaders(candidates: list[ContractCandidate]) -> dict[date, ContractCandidate]:
    grouped: dict[date, list[ContractCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.trading_date].append(candidate)

    return {
        trading_date: max(day_candidates, key=lambda item: item.liquidity_score)
        for trading_date, day_candidates in grouped.items()
    }


def detect_main_contract_switch(
    candidates: list[ContractCandidate],
    *,
    current_contract_month: str | None,
    confirmation_days: int = 3,
) -> ContractCandidate | None:
    if confirmation_days < 1:
        raise ValueError("confirmation_days must be >= 1")

    leaders = daily_leaders(candidates)
    if len(leaders) < confirmation_days:
        return None

    ordered_leaders = [leaders[trading_date] for trading_date in sorted(leaders)]
    recent = ordered_leaders[-confirmation_days:]
    candidate_month = recent[-1].contract_month

    if current_contract_month == candidate_month:
        return None

    if all(item.contract_month == candidate_month for item in recent):
        return recent[-1]

    return None
