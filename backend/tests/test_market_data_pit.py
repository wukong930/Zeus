from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.dialects import postgresql

from app.services.market_data.pit import _market_data_pit_statement


def _compile(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_market_data_pit_uses_three_key_keyset_cursor():
    before = datetime(2026, 5, 18, tzinfo=timezone.utc)
    before_id = UUID("00000000-0000-0000-0000-000000000030")
    sql = _compile(
        _market_data_pit_statement(
            symbol="RB",
            before=before,
            before_contract_month="main",
            before_id=before_id,
            limit=20,
        )
    )
    # cursor matches the (timestamp desc, contract_month asc, id desc) output order
    assert "market_data.timestamp < '2026-05-18" in sql
    assert "market_data.contract_month > 'main'" in sql
    assert "market_data.id < '00000000-0000-0000-0000-000000000030'" in sql
    assert (
        "ORDER BY market_data.timestamp DESC, market_data.contract_month ASC, market_data.id DESC"
        in sql
    )


def test_market_data_pit_falls_back_to_timestamp_cursor_without_full_key():
    before = datetime(2026, 5, 18, tzinfo=timezone.utc)
    sql = _compile(_market_data_pit_statement(symbol="RB", before=before, limit=20))
    assert "market_data.timestamp < '2026-05-18" in sql
    assert "market_data.contract_month >" not in sql


def test_market_data_pit_without_cursor_has_no_before_filter():
    sql = _compile(_market_data_pit_statement(symbol="RB", limit=20))
    assert "market_data.timestamp <" not in sql
    assert "market_data.symbol = 'RB'" in sql
