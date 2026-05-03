"""phase3 governance review queue

Revision ID: 20260503_0004
Revises: 20260503_0003
Create Date: 2026-05-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260503_0004"
down_revision: str | None = "20260503_0003"
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
        "change_review_queue",
        _uuid_pk(),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("target_table", sa.String(length=80), nullable=False),
        sa.Column("target_key", sa.String(length=160), nullable=False),
        sa.Column("proposed_change", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text()),
        sa.Column("reviewed_by", sa.String(length=80)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_change_review_queue_source", "change_review_queue", ["source"])
    op.create_index("ix_change_review_queue_status", "change_review_queue", ["status"])
    op.create_index(
        "ix_change_review_queue_target",
        "change_review_queue",
        ["target_table", "target_key"],
    )
    op.create_index("ix_change_review_queue_created_at", "change_review_queue", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_change_review_queue_created_at", table_name="change_review_queue")
    op.drop_index("ix_change_review_queue_target", table_name="change_review_queue")
    op.drop_index("ix_change_review_queue_status", table_name="change_review_queue")
    op.drop_index("ix_change_review_queue_source", table_name="change_review_queue")
    op.drop_table("change_review_queue")
