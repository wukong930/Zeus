"""phase9 shadow mode and threshold calibration

Revision ID: 20260503_0013
Revises: 20260503_0012
Create Date: 2026-05-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260503_0013"
down_revision: str | None = "20260503_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def upgrade() -> None:
    op.create_table(
        "shadow_runs",
        _uuid_pk(),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("algorithm_version", sa.String(length=80), nullable=False),
        sa.Column("config_diff", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(length=80)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_shadow_runs_status", "shadow_runs", ["status"])
    op.create_index("ix_shadow_runs_algorithm_version", "shadow_runs", ["algorithm_version"])
    op.create_index("ix_shadow_runs_window", "shadow_runs", ["started_at", "ended_at"])

    op.create_table(
        "shadow_signals",
        _uuid_pk(),
        sa.Column("shadow_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_event_type", sa.String(length=80), nullable=False),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True)),
        sa.Column("correlation_id", sa.String(length=120)),
        sa.Column("signal_type", sa.String(length=40), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("symbol", sa.String(length=40)),
        sa.Column("would_emit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("score", sa.Float()),
        sa.Column("threshold", sa.Float()),
        sa.Column("production_signal_track_id", postgresql.UUID(as_uuid=True)),
        sa.Column("production_alert_id", postgresql.UUID(as_uuid=True)),
        sa.Column("outcome", sa.String(length=20)),
        sa.Column("reason", sa.Text()),
        sa.Column("signal_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("context_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("score_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_shadow_signals_run", "shadow_signals", ["shadow_run_id"])
    op.create_index(
        "ix_shadow_signals_event",
        "shadow_signals",
        ["source_event_type", "source_event_id"],
    )
    op.create_index(
        "ix_shadow_signals_lookup",
        "shadow_signals",
        ["signal_type", "category", "symbol"],
    )
    op.create_index("ix_shadow_signals_would_emit", "shadow_signals", ["would_emit"])
    op.create_index("ix_shadow_signals_created_at", "shadow_signals", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_shadow_signals_created_at", table_name="shadow_signals")
    op.drop_index("ix_shadow_signals_would_emit", table_name="shadow_signals")
    op.drop_index("ix_shadow_signals_lookup", table_name="shadow_signals")
    op.drop_index("ix_shadow_signals_event", table_name="shadow_signals")
    op.drop_index("ix_shadow_signals_run", table_name="shadow_signals")
    op.drop_table("shadow_signals")

    op.drop_index("ix_shadow_runs_window", table_name="shadow_runs")
    op.drop_index("ix_shadow_runs_algorithm_version", table_name="shadow_runs")
    op.drop_index("ix_shadow_runs_status", table_name="shadow_runs")
    op.drop_table("shadow_runs")
