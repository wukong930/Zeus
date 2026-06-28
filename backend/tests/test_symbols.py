from app.services.data_sources.akshare_futures import _base_symbol
from app.services.symbols import normalize_root_symbol


def test_strips_trailing_contract_month_to_root():
    assert normalize_root_symbol("RB2505") == "RB"
    assert normalize_root_symbol("RB0") == "RB"
    assert normalize_root_symbol("i2501") == "I"
    assert normalize_root_symbol("  ru2509  ") == "RU"


def test_preserves_non_trailing_digits_so_root_is_not_corrupted():
    # Embedded/leading digits are NOT a contract month. The old `\d+` rule
    # collapsed these (6E -> E) and diverged from the write side; the read side
    # must leave them intact.
    assert normalize_root_symbol("6E") == "6E"
    assert normalize_root_symbol("ES1!") == "ES1!"


def test_read_side_matches_write_side_base_symbol():
    # normalize_root_symbol (read) must agree with _base_symbol (write) so a
    # queried symbol resolves to the same root that was stored.
    for raw in ["RB2505", "RB0", "I0", "JM0", "NR0", "6E", "ru2509"]:
        assert normalize_root_symbol(raw) == (_base_symbol(raw) or None)


def test_empty_and_all_digit_symbols_return_none():
    assert normalize_root_symbol("") is None
    assert normalize_root_symbol(None) is None
    assert normalize_root_symbol("   ") is None
    assert normalize_root_symbol("2505") is None
