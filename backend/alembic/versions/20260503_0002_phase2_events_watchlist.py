"""phase2 events and watchlist

Revision ID: 20260503_0002
Revises: 20260503_0001
Create Date: 2026-05-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260503_0002"
down_revision: str | None = "20260503_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


WATCHLIST_ROWS = (
    {"symbol1": "RB", "symbol2": "HC", "category": "ferrous", "priority": 1},
    {"symbol1": "I", "symbol2": "J", "category": "ferrous", "priority": 2},
    {"symbol1": "JM", "symbol2": "J", "category": "ferrous", "priority": 3},
    {"symbol1": "RB", "symbol2": "I", "category": "ferrous", "priority": 4},
    {"symbol1": "SF", "symbol2": "SM", "category": "ferrous", "priority": 5},
    {"symbol1": "RB", "symbol2": None, "category": "ferrous", "priority": 6},
    {"symbol1": "HC", "symbol2": None, "category": "ferrous", "priority": 7},
    {"symbol1": "SS", "symbol2": None, "category": "ferrous", "priority": 8},
    {"symbol1": "I", "symbol2": None, "category": "ferrous", "priority": 9},
    {"symbol1": "J", "symbol2": None, "category": "ferrous", "priority": 10},
    {"symbol1": "JM", "symbol2": None, "category": "ferrous", "priority": 11},
    {"symbol1": "SF", "symbol2": None, "category": "ferrous", "priority": 12},
    {"symbol1": "SM", "symbol2": None, "category": "ferrous", "priority": 13},
    {"symbol1": "CU", "symbol2": "AL", "category": "nonferrous", "priority": 14},
    {"symbol1": "CU", "symbol2": "ZN", "category": "nonferrous", "priority": 15},
    {"symbol1": "NI", "symbol2": "SN", "category": "nonferrous", "priority": 16},
    {"symbol1": "ZN", "symbol2": "PB", "category": "nonferrous", "priority": 17},
    {"symbol1": "CU", "symbol2": None, "category": "nonferrous", "priority": 18},
    {"symbol1": "AL", "symbol2": None, "category": "nonferrous", "priority": 19},
    {"symbol1": "ZN", "symbol2": None, "category": "nonferrous", "priority": 20},
    {"symbol1": "NI", "symbol2": None, "category": "nonferrous", "priority": 21},
    {"symbol1": "SN", "symbol2": None, "category": "nonferrous", "priority": 22},
    {"symbol1": "PB", "symbol2": None, "category": "nonferrous", "priority": 23},
    {"symbol1": "SC", "symbol2": "FU", "category": "energy", "priority": 24},
    {"symbol1": "SC", "symbol2": "LU", "category": "energy", "priority": 25},
    {"symbol1": "TA", "symbol2": "MEG", "category": "energy", "priority": 26},
    {"symbol1": "PP", "symbol2": "L", "category": "energy", "priority": 27},
    {"symbol1": "EB", "symbol2": "TA", "category": "energy", "priority": 28},
    {"symbol1": "MA", "symbol2": "MEG", "category": "energy", "priority": 29},
    {"symbol1": "SC", "symbol2": None, "category": "energy", "priority": 30},
    {"symbol1": "FU", "symbol2": None, "category": "energy", "priority": 31},
    {"symbol1": "LU", "symbol2": None, "category": "energy", "priority": 32},
    {"symbol1": "BU", "symbol2": None, "category": "energy", "priority": 33},
    {"symbol1": "PP", "symbol2": None, "category": "energy", "priority": 34},
    {"symbol1": "TA", "symbol2": None, "category": "energy", "priority": 35},
    {"symbol1": "MEG", "symbol2": None, "category": "energy", "priority": 36},
    {"symbol1": "MA", "symbol2": None, "category": "energy", "priority": 37},
    {"symbol1": "EB", "symbol2": None, "category": "energy", "priority": 38},
    {"symbol1": "PG", "symbol2": None, "category": "energy", "priority": 39},
    {"symbol1": "SA", "symbol2": None, "category": "energy", "priority": 40},
    {"symbol1": "UR", "symbol2": None, "category": "energy", "priority": 41},
    {"symbol1": "V", "symbol2": None, "category": "energy", "priority": 42},
    {"symbol1": "L", "symbol2": None, "category": "energy", "priority": 43},
    {"symbol1": "P", "symbol2": "Y", "category": "agriculture", "priority": 44},
    {"symbol1": "M", "symbol2": "RM", "category": "agriculture", "priority": 45},
    {"symbol1": "Y", "symbol2": "OI", "category": "agriculture", "priority": 46},
    {"symbol1": "C", "symbol2": "CS", "category": "agriculture", "priority": 47},
    {"symbol1": "CF", "symbol2": "SR", "category": "agriculture", "priority": 48},
    {"symbol1": "P", "symbol2": None, "category": "agriculture", "priority": 49},
    {"symbol1": "Y", "symbol2": None, "category": "agriculture", "priority": 50},
    {"symbol1": "M", "symbol2": None, "category": "agriculture", "priority": 51},
    {"symbol1": "OI", "symbol2": None, "category": "agriculture", "priority": 52},
    {"symbol1": "RM", "symbol2": None, "category": "agriculture", "priority": 53},
    {"symbol1": "CF", "symbol2": None, "category": "agriculture", "priority": 54},
    {"symbol1": "SR", "symbol2": None, "category": "agriculture", "priority": 55},
    {"symbol1": "AP", "symbol2": None, "category": "agriculture", "priority": 56},
    {"symbol1": "C", "symbol2": None, "category": "agriculture", "priority": 57},
    {"symbol1": "CS", "symbol2": None, "category": "agriculture", "priority": 58},
    {"symbol1": "JD", "symbol2": None, "category": "agriculture", "priority": 59},
    {"symbol1": "LH", "symbol2": None, "category": "agriculture", "priority": 60},
    {"symbol1": "SP", "symbol2": None, "category": "agriculture", "priority": 61},
    {"symbol1": "PK", "symbol2": None, "category": "agriculture", "priority": 62},
    {"symbol1": "AU", "symbol2": "AG", "category": "nonferrous", "priority": 63},
    {"symbol1": "AU", "symbol2": None, "category": "nonferrous", "priority": 64},
    {"symbol1": "AG", "symbol2": None, "category": "nonferrous", "priority": 65},
    {"symbol1": "SI", "symbol2": "SA", "category": "energy", "priority": 66},
    {"symbol1": "LC", "symbol2": "NI", "category": "nonferrous", "priority": 67},
    {"symbol1": "SI", "symbol2": None, "category": "energy", "priority": 68},
    {"symbol1": "LC", "symbol2": None, "category": "nonferrous", "priority": 69},
    {"symbol1": "IF", "symbol2": "IH", "category": "financial", "priority": 70},
    {"symbol1": "IF", "symbol2": "IC", "category": "financial", "priority": 71},
    {"symbol1": "IC", "symbol2": "IM", "category": "financial", "priority": 72},
    {"symbol1": "T", "symbol2": "TF", "category": "financial", "priority": 73},
    {"symbol1": "TF", "symbol2": "TS", "category": "financial", "priority": 74},
    {"symbol1": "IF", "symbol2": None, "category": "financial", "priority": 75},
    {"symbol1": "IC", "symbol2": None, "category": "financial", "priority": 76},
    {"symbol1": "IM", "symbol2": None, "category": "financial", "priority": 77},
    {"symbol1": "IH", "symbol2": None, "category": "financial", "priority": 78},
    {"symbol1": "TS", "symbol2": None, "category": "financial", "priority": 79},
    {"symbol1": "TF", "symbol2": None, "category": "financial", "priority": 80},
    {"symbol1": "T", "symbol2": None, "category": "financial", "priority": 81},
    {"symbol1": "TL", "symbol2": None, "category": "financial", "priority": 82},
    {"symbol1": "AU", "symbol2": "GC", "category": "nonferrous", "priority": 83},
    {"symbol1": "CU", "symbol2": "HG", "category": "nonferrous", "priority": 84},
    {"symbol1": "SC", "symbol2": "CL", "category": "energy", "priority": 85},
    {"symbol1": "CF", "symbol2": "CT", "category": "agriculture", "priority": 86},
    {"symbol1": "SR", "symbol2": "SB", "category": "agriculture", "priority": 87},
    {"symbol1": "CU", "symbol2": "LME_CU", "category": "nonferrous", "priority": 88},
    {"symbol1": "AL", "symbol2": "LME_AL", "category": "nonferrous", "priority": 89},
    {"symbol1": "GC", "symbol2": None, "category": "overseas", "priority": 90},
    {"symbol1": "SI_F", "symbol2": None, "category": "overseas", "priority": 91},
    {"symbol1": "HG", "symbol2": None, "category": "overseas", "priority": 92},
    {"symbol1": "NG", "symbol2": None, "category": "overseas", "priority": 93},
    {"symbol1": "S", "symbol2": None, "category": "overseas", "priority": 94},
    {"symbol1": "W", "symbol2": None, "category": "overseas", "priority": 95},
    {"symbol1": "CT", "symbol2": None, "category": "overseas", "priority": 96},
    {"symbol1": "SB", "symbol2": None, "category": "overseas", "priority": 97},
    {"symbol1": "CC", "symbol2": None, "category": "overseas", "priority": 98},
    {"symbol1": "LME_CU", "symbol2": None, "category": "overseas", "priority": 99},
    {"symbol1": "LME_AL", "symbol2": None, "category": "overseas", "priority": 100},
    {"symbol1": "LME_ZN", "symbol2": None, "category": "overseas", "priority": 101},
    {"symbol1": "LME_NI", "symbol2": None, "category": "overseas", "priority": 102},
)


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def upgrade() -> None:
    op.create_table(
        "event_log",
        _uuid_pk(),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("correlation_id", sa.String(length=80), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_event_log_channel", "event_log", ["channel"])
    op.create_index("ix_event_log_status", "event_log", ["status"])
    op.create_index("ix_event_log_correlation_id", "event_log", ["correlation_id"])
    op.create_index("ix_event_log_created_at", "event_log", ["created_at"])

    op.create_table(
        "watchlist",
        _uuid_pk(),
        sa.Column("symbol1", sa.Text(), nullable=False),
        sa.Column("symbol2", sa.Text()),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column(
            "custom_thresholds",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("position_linked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_watchlist_enabled_category", "watchlist", ["enabled", "category"])
    op.create_index("ix_watchlist_symbol1", "watchlist", ["symbol1"])
    op.create_index("ix_watchlist_symbol_pair", "watchlist", ["symbol1", "symbol2"])
    op.execute(
        "CREATE UNIQUE INDEX uq_watchlist_symbol_pair_category "
        "ON watchlist (symbol1, COALESCE(symbol2, ''), category)"
    )

    watchlist_table = sa.table(
        "watchlist",
        sa.column("symbol1", sa.Text()),
        sa.column("symbol2", sa.Text()),
        sa.column("category", sa.String(length=20)),
        sa.column("priority", sa.Integer()),
        sa.column("custom_thresholds", postgresql.JSONB()),
    )
    op.bulk_insert(
        watchlist_table,
        [{**row, "custom_thresholds": {}} for row in WATCHLIST_ROWS],
    )


def downgrade() -> None:
    op.drop_index("uq_watchlist_symbol_pair_category", table_name="watchlist")
    op.drop_index("ix_watchlist_symbol_pair", table_name="watchlist")
    op.drop_index("ix_watchlist_symbol1", table_name="watchlist")
    op.drop_index("ix_watchlist_enabled_category", table_name="watchlist")
    op.drop_table("watchlist")
    op.drop_index("ix_event_log_created_at", table_name="event_log")
    op.drop_index("ix_event_log_correlation_id", table_name="event_log")
    op.drop_index("ix_event_log_status", table_name="event_log")
    op.drop_index("ix_event_log_channel", table_name="event_log")
    op.drop_table("event_log")
