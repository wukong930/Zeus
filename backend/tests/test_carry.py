import math

import pytest

from app.services.backtest.carry import carry_signal, contract_maturity


def test_contract_maturity_parses_yymm():
    assert contract_maturity("rb2410") == (2024, 10)
    assert contract_maturity("CU2501") == (2025, 1)
    assert contract_maturity("AU0") is None  # no 4-digit maturity
    assert contract_maturity("rb2413") is None  # invalid month


def test_carry_signal_backwardation_positive():
    # front (2410) richer than next (2411) -> positive annualized carry
    contracts = {"rb2410": (3000.0, 1_000_000.0), "rb2411": (2950.0, 500_000.0)}
    carry = carry_signal(contracts)
    assert carry == pytest.approx(math.log(3000 / 2950) / 1 * 12)
    assert carry > 0


def test_carry_signal_contango_negative():
    contracts = {"rb2410": (2950.0, 1_000_000.0), "rb2411": (3000.0, 500_000.0)}
    assert carry_signal(contracts) < 0


def test_carry_signal_needs_two_liquid_contracts():
    assert carry_signal({"rb2410": (3000.0, 1_000_000.0)}) is None
    # the far contract is filtered out by the OI floor -> only one liquid -> None
    contracts = {"rb2410": (3000.0, 1_000_000.0), "rb2411": (2950.0, 10.0)}
    assert carry_signal(contracts, min_oi=1000.0) is None
