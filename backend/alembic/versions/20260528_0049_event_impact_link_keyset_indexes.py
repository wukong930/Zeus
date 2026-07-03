"""add event impact link keyset pagination indexes

Revision ID: 20260528_0049
Revises: 20260526_0048
Create Date: 2026-05-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260528_0049"
down_revision: str | None = "20260526_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_event_impact_links_symbol_score_id",
        "event_impact_links",
        ["symbol", "impact_score", "confidence", "id"],
    )
    op.create_index(
        "ix_event_impact_links_region_score_id",
        "event_impact_links",
        ["region_id", "impact_score", "confidence", "id"],
    )
    op.create_index(
        "ix_event_impact_links_mechanism_score_id",
        "event_impact_links",
        ["mechanism", "impact_score", "confidence", "id"],
    )
    op.create_index(
        "ix_event_impact_links_status_score_id",
        "event_impact_links",
        ["status", "impact_score", "confidence", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_event_impact_links_status_score_id", table_name="event_impact_links")
    op.drop_index("ix_event_impact_links_mechanism_score_id", table_name="event_impact_links")
    op.drop_index("ix_event_impact_links_region_score_id", table_name="event_impact_links")
    op.drop_index("ix_event_impact_links_symbol_score_id", table_name="event_impact_links")
