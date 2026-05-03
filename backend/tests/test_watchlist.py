import importlib.util
from collections import Counter
from pathlib import Path

from app.models.watchlist import Watchlist
from app.services.signals.watchlist import (
    WatchlistEntry,
    normalize_symbol,
    to_watchlist_entry,
)


def test_watchlist_entry_key_uses_symbol_pair_and_category() -> None:
    entry = WatchlistEntry(symbol1="RB", symbol2="HC", category="ferrous")

    assert entry.symbols == ("RB", "HC")
    assert entry.key == "RB:HC:ferrous"


def test_normalize_symbol_strips_and_uppercases() -> None:
    assert normalize_symbol(" rb ") == "RB"
    assert normalize_symbol(" ") is None
    assert normalize_symbol(None) is None


def test_to_watchlist_entry_maps_orm_row() -> None:
    row = Watchlist(
        symbol1="CU",
        symbol2="AL",
        category="nonferrous",
        priority=14,
        custom_thresholds={"z_score": 2.5},
        position_linked=True,
    )

    entry = to_watchlist_entry(row)

    assert entry == WatchlistEntry(
        symbol1="CU",
        symbol2="AL",
        category="nonferrous",
        priority=14,
        custom_thresholds={"z_score": 2.5},
        position_linked=True,
    )


def test_phase2_migration_seeds_current_causa_watchlist() -> None:
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20260503_0002_phase2_events_watchlist.py"
    )
    spec = importlib.util.spec_from_file_location("phase2_events_watchlist", migration_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    rows = module.WATCHLIST_ROWS
    counts = Counter(row["category"] for row in rows)

    assert len(rows) == 102
    assert counts == {
        "agriculture": 21,
        "energy": 23,
        "ferrous": 13,
        "financial": 13,
        "nonferrous": 19,
        "overseas": 13,
    }
