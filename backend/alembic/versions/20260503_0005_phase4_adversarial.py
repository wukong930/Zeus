"""phase4 adversarial engine

Revision ID: 20260503_0005
Revises: 20260503_0004
Create Date: 2026-05-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260503_0005"
down_revision: str | None = "20260503_0004"
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
        "adversarial_results",
        _uuid_pk(),
        sa.Column("signal_type", sa.String(length=30), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("regime", sa.String(length=40), nullable=False),
        sa.Column("signal_combination_hash", sa.String(length=64)),
        sa.Column("signal_track_id", postgresql.UUID(as_uuid=True)),
        sa.Column("correlation_id", sa.String(length=80)),
        sa.Column("null_hypothesis_pvalue", sa.Float()),
        sa.Column("null_hypothesis_passed", sa.Boolean()),
        sa.Column("historical_combo_hit_rate", sa.Float()),
        sa.Column("historical_combo_sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "historical_combo_mode",
            sa.String(length=20),
            nullable=False,
            server_default="informational",
        ),
        sa.Column("historical_combo_passed", sa.Boolean()),
        sa.Column("structural_counter_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("structural_counter_passed", sa.Boolean()),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("suppressed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("confidence_multiplier", sa.Float(), nullable=False, server_default="1"),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_adversarial_results_signal",
        "adversarial_results",
        ["signal_type", "category", "regime"],
    )
    op.create_index(
        "ix_adversarial_results_combination_hash",
        "adversarial_results",
        ["signal_combination_hash"],
    )
    op.create_index("ix_adversarial_results_passed", "adversarial_results", ["passed"])
    op.create_index(
        "ix_adversarial_results_computed_at",
        "adversarial_results",
        ["computed_at"],
    )

    op.create_table(
        "null_distribution_cache",
        _uuid_pk(),
        sa.Column("signal_type", sa.String(length=30), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("computed_for", sa.Date(), nullable=False),
        sa.Column(
            "statistic_name",
            sa.String(length=40),
            nullable=False,
            server_default="signal_strength",
        ),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pvalue_threshold", sa.Float(), nullable=False, server_default="0.05"),
        sa.Column("distribution_stats", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "signal_type",
            "category",
            "computed_for",
            name="uq_null_distribution_signal_category_date",
        ),
    )
    op.create_index(
        "ix_null_distribution_lookup",
        "null_distribution_cache",
        ["signal_type", "category", "computed_for"],
    )
    op.create_index(
        "ix_null_distribution_computed_at",
        "null_distribution_cache",
        ["computed_at"],
    )

    op.add_column(
        "alerts",
        sa.Column("adversarial_passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_alerts_adversarial_passed", "alerts", ["adversarial_passed"])
    op.add_column("signal_track", sa.Column("adversarial_passed", sa.Boolean()))


def downgrade() -> None:
    op.drop_column("signal_track", "adversarial_passed")
    op.drop_index("ix_alerts_adversarial_passed", table_name="alerts")
    op.drop_column("alerts", "adversarial_passed")

    op.drop_index("ix_null_distribution_computed_at", table_name="null_distribution_cache")
    op.drop_index("ix_null_distribution_lookup", table_name="null_distribution_cache")
    op.drop_table("null_distribution_cache")

    op.drop_index("ix_adversarial_results_computed_at", table_name="adversarial_results")
    op.drop_index("ix_adversarial_results_passed", table_name="adversarial_results")
    op.drop_index("ix_adversarial_results_combination_hash", table_name="adversarial_results")
    op.drop_index("ix_adversarial_results_signal", table_name="adversarial_results")
    op.drop_table("adversarial_results")
