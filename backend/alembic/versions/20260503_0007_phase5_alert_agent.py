"""phase5 alert agent and learning controls

Revision ID: 20260503_0007
Revises: 20260503_0006
Create Date: 2026-05-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260503_0007"
down_revision: str | None = "20260503_0006"
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
    op.add_column(
        "alerts",
        sa.Column("llm_involved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "alerts",
        sa.Column("confidence_tier", sa.String(length=20), nullable=False, server_default="notify"),
    )
    op.add_column(
        "alerts",
        sa.Column(
            "human_action_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("alerts", sa.Column("human_action_deadline", sa.DateTime(timezone=True)))
    op.add_column(
        "alerts",
        sa.Column("dedup_suppressed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_alerts_confidence_tier", "alerts", ["confidence_tier"])
    op.create_index("ix_alerts_human_action_required", "alerts", ["human_action_required"])
    op.create_index("ix_alerts_dedup_suppressed", "alerts", ["dedup_suppressed"])

    op.create_table(
        "alert_dedup_cache",
        _uuid_pk(),
        sa.Column("symbol", sa.String(length=40), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("evaluator", sa.String(length=40), nullable=False),
        sa.Column("signal_combination_hash", sa.String(length=64)),
        sa.Column("last_emitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_severity", sa.String(length=20), nullable=False),
        sa.Column("last_score", sa.Integer()),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "symbol",
            "direction",
            "evaluator",
            name="uq_alert_dedup_symbol_direction_evaluator",
        ),
    )
    op.create_index(
        "ix_alert_dedup_lookup",
        "alert_dedup_cache",
        ["symbol", "direction", "evaluator"],
    )
    op.create_index(
        "ix_alert_dedup_signal_hash",
        "alert_dedup_cache",
        ["signal_combination_hash"],
    )
    op.create_index(
        "ix_alert_dedup_last_emitted_at",
        "alert_dedup_cache",
        ["last_emitted_at"],
    )

    op.create_table(
        "alert_agent_config",
        _uuid_pk(),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("key", name="uq_alert_agent_config_key"),
    )
    op.create_index("ix_alert_agent_config_key", "alert_agent_config", ["key"])
    op.bulk_insert(
        sa.table(
            "alert_agent_config",
            sa.column("key", sa.String(length=80)),
            sa.column("value", postgresql.JSONB()),
        ),
        [
            {
                "key": "confidence_thresholds",
                "value": {"auto": 0.85, "notify": 0.60},
            }
        ],
    )

    op.create_table(
        "llm_cache",
        _uuid_pk(),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("module", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("system_hash", sa.String(length=64), nullable=False),
        sa.Column("user_hash", sa.String(length=64), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("cache_key", name="uq_llm_cache_key"),
    )
    op.create_index("ix_llm_cache_module", "llm_cache", ["module"])
    op.create_index("ix_llm_cache_expires_at", "llm_cache", ["expires_at"])
    op.create_index("ix_llm_cache_provider_model", "llm_cache", ["provider", "model"])

    op.create_table(
        "llm_usage_log",
        _uuid_pk(),
        sa.Column("module", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ok"),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_llm_usage_module_created", "llm_usage_log", ["module", "created_at"])
    op.create_index("ix_llm_usage_provider_model", "llm_usage_log", ["provider", "model"])
    op.create_index("ix_llm_usage_cache_hit", "llm_usage_log", ["cache_hit"])

    op.create_table(
        "llm_budgets",
        _uuid_pk(),
        sa.Column("module", sa.String(length=40), nullable=False),
        sa.Column("monthly_budget_usd", sa.Float(), nullable=False),
        sa.Column("current_spend_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("alert_threshold", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("module", "period_start", name="uq_llm_budget_module_period"),
    )
    op.create_index("ix_llm_budgets_module", "llm_budgets", ["module"])
    op.create_index("ix_llm_budgets_status", "llm_budgets", ["status"])

    op.create_table(
        "human_decisions",
        _uuid_pk(),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True)),
        sa.Column("signal_track_id", postgresql.UUID(as_uuid=True)),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("confidence_override", sa.Float()),
        sa.Column("reasoning", sa.Text()),
        sa.Column("decided_by", sa.String(length=80)),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_human_decisions_alert_id", "human_decisions", ["alert_id"])
    op.create_index("ix_human_decisions_decision", "human_decisions", ["decision"])
    op.create_index("ix_human_decisions_created_at", "human_decisions", ["created_at"])

    op.create_table(
        "user_feedback",
        _uuid_pk(),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True)),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("signal_type", sa.String(length=40)),
        sa.Column("category", sa.String(length=40)),
        sa.Column("agree", sa.String(length=20), nullable=False),
        sa.Column("disagreement_reason", sa.Text()),
        sa.Column("will_trade", sa.String(length=20), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_feedback_alert_id", "user_feedback", ["alert_id"])
    op.create_index("ix_user_feedback_recommendation_id", "user_feedback", ["recommendation_id"])
    op.create_index("ix_user_feedback_signal_type", "user_feedback", ["signal_type"])
    op.create_index("ix_user_feedback_recorded_at", "user_feedback", ["recorded_at"])


def downgrade() -> None:
    op.drop_index("ix_user_feedback_recorded_at", table_name="user_feedback")
    op.drop_index("ix_user_feedback_signal_type", table_name="user_feedback")
    op.drop_index("ix_user_feedback_recommendation_id", table_name="user_feedback")
    op.drop_index("ix_user_feedback_alert_id", table_name="user_feedback")
    op.drop_table("user_feedback")

    op.drop_index("ix_human_decisions_created_at", table_name="human_decisions")
    op.drop_index("ix_human_decisions_decision", table_name="human_decisions")
    op.drop_index("ix_human_decisions_alert_id", table_name="human_decisions")
    op.drop_table("human_decisions")

    op.drop_index("ix_llm_budgets_status", table_name="llm_budgets")
    op.drop_index("ix_llm_budgets_module", table_name="llm_budgets")
    op.drop_table("llm_budgets")

    op.drop_index("ix_llm_usage_cache_hit", table_name="llm_usage_log")
    op.drop_index("ix_llm_usage_provider_model", table_name="llm_usage_log")
    op.drop_index("ix_llm_usage_module_created", table_name="llm_usage_log")
    op.drop_table("llm_usage_log")

    op.drop_index("ix_llm_cache_provider_model", table_name="llm_cache")
    op.drop_index("ix_llm_cache_expires_at", table_name="llm_cache")
    op.drop_index("ix_llm_cache_module", table_name="llm_cache")
    op.drop_table("llm_cache")

    op.drop_index("ix_alert_agent_config_key", table_name="alert_agent_config")
    op.drop_table("alert_agent_config")

    op.drop_index("ix_alert_dedup_last_emitted_at", table_name="alert_dedup_cache")
    op.drop_index("ix_alert_dedup_signal_hash", table_name="alert_dedup_cache")
    op.drop_index("ix_alert_dedup_lookup", table_name="alert_dedup_cache")
    op.drop_table("alert_dedup_cache")

    op.drop_index("ix_alerts_dedup_suppressed", table_name="alerts")
    op.drop_index("ix_alerts_human_action_required", table_name="alerts")
    op.drop_index("ix_alerts_confidence_tier", table_name="alerts")
    op.drop_column("alerts", "dedup_suppressed")
    op.drop_column("alerts", "human_action_deadline")
    op.drop_column("alerts", "human_action_required")
    op.drop_column("alerts", "confidence_tier")
    op.drop_column("alerts", "llm_involved")
