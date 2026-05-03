"""phase1 core schema

Revision ID: 20260503_0001
Revises:
Create Date: 2026-05-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260503_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    op.create_table(
        "contract_metadata",
        _uuid_pk(),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("exchange", sa.String(length=20)),
        sa.Column("commodity", sa.Text()),
        sa.Column("contract_month", sa.String(length=20), nullable=False),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("is_main", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("main_from", sa.DateTime(timezone=True)),
        sa.Column("main_until", sa.DateTime(timezone=True)),
        sa.Column("volume", sa.Float()),
        sa.Column("open_interest", sa.Float()),
        *_timestamps(),
        sa.UniqueConstraint("symbol", "contract_month", name="uq_contract_symbol_month"),
    )
    op.create_index("ix_contract_metadata_symbol", "contract_metadata", ["symbol"])
    op.create_index("ix_contract_metadata_is_main", "contract_metadata", ["symbol", "is_main"])
    op.create_index("ix_contract_metadata_expiry", "contract_metadata", ["expiry_date"])

    op.create_table(
        "strategies",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("hypothesis", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("validation", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "related_alert_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "recommendation_history",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "execution_feedback_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        *_timestamps(),
        sa.Column("last_activated_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
    )
    op.create_index("ix_strategies_status", "strategies", ["status"])
    op.create_index("ix_strategies_created_at", "strategies", ["created_at"])

    op.create_table(
        "research_hypotheses",
        _uuid_pk(),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_research_hypotheses_status", "research_hypotheses", ["status"])
    op.create_index("ix_research_hypotheses_created_at", "research_hypotheses", ["created_at"])

    op.create_table(
        "research_reports",
        _uuid_pk(),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("hypotheses", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "related_strategy_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "related_alert_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_research_reports_type", "research_reports", ["type"])
    op.create_index("ix_research_reports_published_at", "research_reports", ["published_at"])

    op.create_table(
        "alerts",
        _uuid_pk(),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("related_assets", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("spread_info", postgresql.JSONB()),
        sa.Column("trigger_chain", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("risk_items", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "manual_check_items",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("one_liner", sa.Text()),
        sa.Column(
            "related_strategy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategies.id", ondelete="SET NULL"),
        ),
        sa.Column("related_recommendation_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "related_research_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_reports.id", ondelete="SET NULL"),
        ),
        sa.Column("invalidation_reason", sa.Text()),
    )
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_index("ix_alerts_category", "alerts", ["category"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_triggered_at", "alerts", ["triggered_at"])

    op.create_table(
        "recommendations",
        _uuid_pk(),
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("strategies.id", ondelete="SET NULL")),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("alerts.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("recommended_action", sa.String(length=20), nullable=False),
        sa.Column("legs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("priority_score", sa.Float(), nullable=False),
        sa.Column("portfolio_fit_score", sa.Float(), nullable=False),
        sa.Column("margin_efficiency_score", sa.Float(), nullable=False),
        sa.Column("margin_required", sa.Float(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("one_liner", sa.Text()),
        sa.Column("risk_items", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.Column("deferred_until", sa.DateTime(timezone=True)),
        sa.Column("ignored_reason", sa.Text()),
        sa.Column("execution_feedback_id", postgresql.UUID(as_uuid=True)),
        sa.Column("max_holding_days", sa.Integer()),
        sa.Column("position_size_pct", sa.Float()),
        sa.Column("risk_reward_ratio", sa.Float()),
        sa.Column("backtest_summary", postgresql.JSONB()),
    )
    op.create_index("ix_recommendations_status", "recommendations", ["status"])
    op.create_index("ix_recommendations_strategy_id", "recommendations", ["strategy_id"])
    op.create_index("ix_recommendations_alert_id", "recommendations", ["alert_id"])
    op.create_index("ix_recommendations_created_at", "recommendations", ["created_at"])

    op.create_table(
        "positions",
        _uuid_pk(),
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("strategies.id", ondelete="SET NULL")),
        sa.Column("strategy_name", sa.Text()),
        sa.Column(
            "recommendation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recommendations.id", ondelete="SET NULL"),
        ),
        sa.Column("legs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_spread", sa.Float(), nullable=False),
        sa.Column("current_spread", sa.Float(), nullable=False),
        sa.Column("spread_unit", sa.Text(), nullable=False),
        sa.Column("unrealized_pnl", sa.Float(), nullable=False),
        sa.Column("total_margin_used", sa.Float(), nullable=False),
        sa.Column("exit_condition", sa.Text(), nullable=False),
        sa.Column("target_z_score", sa.Float(), nullable=False),
        sa.Column("current_z_score", sa.Float(), nullable=False),
        sa.Column("half_life_days", sa.Float(), nullable=False),
        sa.Column("days_held", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("realized_pnl", sa.Float()),
    )
    op.create_index("ix_positions_status", "positions", ["status"])
    op.create_index("ix_positions_strategy_id", "positions", ["strategy_id"])
    op.create_index("ix_positions_opened_at", "positions", ["opened_at"])

    op.create_table(
        "market_data",
        _uuid_pk(),
        sa.Column("source_key", sa.Text()),
        sa.Column("market", sa.String(length=10), nullable=False),
        sa.Column("exchange", sa.String(length=20), nullable=False),
        sa.Column("commodity", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("contract_month", sa.String(length=20), nullable=False),
        sa.Column(
            "contract_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contract_metadata.id", ondelete="SET NULL"),
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("settle", sa.Float()),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("open_interest", sa.Float()),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="CNY"),
        sa.Column("timezone", sa.Text(), nullable=False, server_default="Asia/Shanghai"),
        sa.Column("vintage_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_market_data_symbol", "market_data", ["symbol"])
    op.create_index("ix_market_data_timestamp", "market_data", ["timestamp"])
    op.create_index("ix_market_data_symbol_timestamp", "market_data", ["symbol", "timestamp"])
    op.create_index("ix_market_data_pit", "market_data", ["symbol", "timestamp", "vintage_at"])
    op.create_index("ix_market_data_contract_id", "market_data", ["contract_id"])

    op.create_table(
        "industry_data",
        _uuid_pk(),
        sa.Column("source_key", sa.Text()),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("data_type", sa.String(length=30), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vintage_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_industry_data_symbol", "industry_data", ["symbol"])
    op.create_index("ix_industry_data_type", "industry_data", ["data_type"])
    op.create_index("ix_industry_data_symbol_type", "industry_data", ["symbol", "data_type"])
    op.create_index("ix_industry_data_pit", "industry_data", ["symbol", "data_type", "timestamp", "vintage_at"])

    op.create_table(
        "signal_track",
        _uuid_pk(),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True)),
        sa.Column("signal_type", sa.String(length=30), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("z_score", sa.Float()),
        sa.Column("regime", sa.String(length=30)),
        sa.Column("outcome", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("position_id", postgresql.UUID(as_uuid=True)),
        sa.Column("forward_return_1d", sa.Float()),
        sa.Column("forward_return_5d", sa.Float()),
        sa.Column("forward_return_20d", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_signal_track_type", "signal_track", ["signal_type"])
    op.create_index("ix_signal_track_category", "signal_track", ["category"])
    op.create_index("ix_signal_track_outcome", "signal_track", ["outcome"])
    op.create_index("ix_signal_track_alert_id", "signal_track", ["alert_id"])

    op.create_table(
        "sector_assessments",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("sector", sa.String(length=20), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("conviction_score", sa.Float(), nullable=False),
        sa.Column("conviction_direction", sa.Integer(), nullable=False),
        sa.Column("supporting_factors", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("opposing_factors", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("data_gaps", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("cost_floor", sa.Float()),
        sa.Column("production_margin", sa.Float()),
        sa.Column("inventory_deviation", sa.Float()),
        sa.Column("seasonal_factor", sa.Float()),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sector_assessments_sector", "sector_assessments", ["sector"])
    op.create_index("ix_sector_assessments_symbol", "sector_assessments", ["symbol"])
    op.create_index("ix_sector_assessments_sector_symbol", "sector_assessments", ["sector", "symbol"])

    op.create_table(
        "commodity_nodes",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False, unique=True),
        sa.Column("cluster", sa.String(length=20), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("active_alert_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("regime", sa.Text(), nullable=False),
        sa.Column("price_change_24h", sa.Float()),
    )
    op.create_index("ix_commodity_nodes_cluster", "commodity_nodes", ["cluster"])
    op.create_index("ix_commodity_nodes_symbol", "commodity_nodes", ["symbol"])

    op.create_table(
        "relationship_edges",
        _uuid_pk(),
        sa.Column(
            "source",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("commodity_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("commodity_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("strength", sa.Float(), nullable=False),
        sa.Column("label", sa.Text()),
        sa.Column("active_alert_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("influence_weight", sa.Float()),
        sa.Column("lag_days", sa.Integer()),
        sa.Column("propagation_direction", sa.Integer()),
    )
    op.create_index("ix_relationship_edges_source", "relationship_edges", ["source"])
    op.create_index("ix_relationship_edges_target", "relationship_edges", ["target"])

    op.create_table(
        "llm_config",
        _uuid_pk(),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("base_url", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_timestamps(),
    )

    op.execute(
        """
        CREATE VIEW market_data_latest AS
        SELECT DISTINCT ON (symbol, contract_month, timestamp) *
        FROM market_data
        ORDER BY symbol, contract_month, timestamp, vintage_at DESC, ingested_at DESC
        """
    )
    op.execute(
        """
        CREATE VIEW industry_data_latest AS
        SELECT DISTINCT ON (symbol, data_type, timestamp) *
        FROM industry_data
        ORDER BY symbol, data_type, timestamp, vintage_at DESC, ingested_at DESC
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS industry_data_latest")
    op.execute("DROP VIEW IF EXISTS market_data_latest")
    op.drop_table("llm_config")
    op.drop_index("ix_relationship_edges_target", table_name="relationship_edges")
    op.drop_index("ix_relationship_edges_source", table_name="relationship_edges")
    op.drop_table("relationship_edges")
    op.drop_index("ix_commodity_nodes_symbol", table_name="commodity_nodes")
    op.drop_index("ix_commodity_nodes_cluster", table_name="commodity_nodes")
    op.drop_table("commodity_nodes")
    op.drop_index("ix_sector_assessments_sector_symbol", table_name="sector_assessments")
    op.drop_index("ix_sector_assessments_symbol", table_name="sector_assessments")
    op.drop_index("ix_sector_assessments_sector", table_name="sector_assessments")
    op.drop_table("sector_assessments")
    op.drop_index("ix_signal_track_alert_id", table_name="signal_track")
    op.drop_index("ix_signal_track_outcome", table_name="signal_track")
    op.drop_index("ix_signal_track_category", table_name="signal_track")
    op.drop_index("ix_signal_track_type", table_name="signal_track")
    op.drop_table("signal_track")
    op.drop_index("ix_industry_data_pit", table_name="industry_data")
    op.drop_index("ix_industry_data_symbol_type", table_name="industry_data")
    op.drop_index("ix_industry_data_type", table_name="industry_data")
    op.drop_index("ix_industry_data_symbol", table_name="industry_data")
    op.drop_table("industry_data")
    op.drop_index("ix_market_data_contract_id", table_name="market_data")
    op.drop_index("ix_market_data_pit", table_name="market_data")
    op.drop_index("ix_market_data_symbol_timestamp", table_name="market_data")
    op.drop_index("ix_market_data_timestamp", table_name="market_data")
    op.drop_index("ix_market_data_symbol", table_name="market_data")
    op.drop_table("market_data")
    op.drop_index("ix_positions_opened_at", table_name="positions")
    op.drop_index("ix_positions_strategy_id", table_name="positions")
    op.drop_index("ix_positions_status", table_name="positions")
    op.drop_table("positions")
    op.drop_index("ix_recommendations_created_at", table_name="recommendations")
    op.drop_index("ix_recommendations_alert_id", table_name="recommendations")
    op.drop_index("ix_recommendations_strategy_id", table_name="recommendations")
    op.drop_index("ix_recommendations_status", table_name="recommendations")
    op.drop_table("recommendations")
    op.drop_index("ix_alerts_triggered_at", table_name="alerts")
    op.drop_index("ix_alerts_severity", table_name="alerts")
    op.drop_index("ix_alerts_category", table_name="alerts")
    op.drop_index("ix_alerts_status", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_research_reports_published_at", table_name="research_reports")
    op.drop_index("ix_research_reports_type", table_name="research_reports")
    op.drop_table("research_reports")
    op.drop_index("ix_research_hypotheses_created_at", table_name="research_hypotheses")
    op.drop_index("ix_research_hypotheses_status", table_name="research_hypotheses")
    op.drop_table("research_hypotheses")
    op.drop_index("ix_strategies_created_at", table_name="strategies")
    op.drop_index("ix_strategies_status", table_name="strategies")
    op.drop_table("strategies")
    op.drop_index("ix_contract_metadata_expiry", table_name="contract_metadata")
    op.drop_index("ix_contract_metadata_is_main", table_name="contract_metadata")
    op.drop_index("ix_contract_metadata_symbol", table_name="contract_metadata")
    op.drop_table("contract_metadata")
