"""phase3 calibration and drift foundation

Revision ID: 20260503_0003
Revises: 20260503_0002
Create Date: 2026-05-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260503_0003"
down_revision: str | None = "20260503_0002"
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
        "signal_calibration",
        _uuid_pk(),
        sa.Column("signal_type", sa.String(length=30), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("regime", sa.String(length=40), nullable=False),
        sa.Column("base_weight", sa.Float(), nullable=False, server_default="1"),
        sa.Column("effective_weight", sa.Float(), nullable=False, server_default="1"),
        sa.Column("rolling_hit_rate", sa.Float()),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("miss_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("alpha_prior", sa.Float(), nullable=False, server_default="4"),
        sa.Column("beta_prior", sa.Float(), nullable=False, server_default="4"),
        sa.Column("decay_detected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_signal_calibration_lookup",
        "signal_calibration",
        ["signal_type", "category", "regime"],
    )
    op.create_index(
        "ix_signal_calibration_effective",
        "signal_calibration",
        ["effective_from", "effective_to"],
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_signal_calibration_active "
        "ON signal_calibration (signal_type, category, regime) WHERE effective_to IS NULL"
    )

    op.create_table(
        "regime_state",
        _uuid_pk(),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("regime", sa.String(length=40), nullable=False),
        sa.Column("adx", sa.Float(), nullable=False),
        sa.Column("atr_percentile", sa.Float(), nullable=False),
        sa.Column("trend_direction", sa.String(length=10), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("category", "as_of_date", name="uq_regime_state_category_date"),
    )
    op.create_index("ix_regime_state_category_date", "regime_state", ["category", "as_of_date"])
    op.create_index("ix_regime_state_regime", "regime_state", ["regime"])

    op.create_table(
        "drift_metrics",
        _uuid_pk(),
        sa.Column("metric_type", sa.String(length=40), nullable=False),
        sa.Column("category", sa.String(length=20)),
        sa.Column("feature_name", sa.String(length=40)),
        sa.Column("current_value", sa.Float()),
        sa.Column("baseline_value", sa.Float()),
        sa.Column("psi", sa.Float()),
        sa.Column("drift_severity", sa.String(length=20), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_drift_metrics_type", "drift_metrics", ["metric_type"])
    op.create_index("ix_drift_metrics_category", "drift_metrics", ["category"])
    op.create_index("ix_drift_metrics_severity", "drift_metrics", ["drift_severity"])
    op.create_index("ix_drift_metrics_computed_at", "drift_metrics", ["computed_at"])

    op.add_column("signal_track", sa.Column("regime_at_emission", sa.String(length=40)))
    op.add_column("signal_track", sa.Column("calibration_weight_at_emission", sa.Float()))
    op.add_column("signal_track", sa.Column("signal_combination_hash", sa.String(length=64)))
    op.create_index("ix_signal_track_combination_hash", "signal_track", ["signal_combination_hash"])
    op.create_index("ix_signal_track_regime_at_emission", "signal_track", ["regime_at_emission"])


def downgrade() -> None:
    op.drop_index("ix_signal_track_regime_at_emission", table_name="signal_track")
    op.drop_index("ix_signal_track_combination_hash", table_name="signal_track")
    op.drop_column("signal_track", "signal_combination_hash")
    op.drop_column("signal_track", "calibration_weight_at_emission")
    op.drop_column("signal_track", "regime_at_emission")

    op.drop_index("ix_drift_metrics_computed_at", table_name="drift_metrics")
    op.drop_index("ix_drift_metrics_severity", table_name="drift_metrics")
    op.drop_index("ix_drift_metrics_category", table_name="drift_metrics")
    op.drop_index("ix_drift_metrics_type", table_name="drift_metrics")
    op.drop_table("drift_metrics")

    op.drop_index("ix_regime_state_regime", table_name="regime_state")
    op.drop_index("ix_regime_state_category_date", table_name="regime_state")
    op.drop_table("regime_state")

    op.drop_index("uq_signal_calibration_active", table_name="signal_calibration")
    op.drop_index("ix_signal_calibration_effective", table_name="signal_calibration")
    op.drop_index("ix_signal_calibration_lookup", table_name="signal_calibration")
    op.drop_table("signal_calibration")
