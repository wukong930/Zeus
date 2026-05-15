"""translation layer for news and alerts

Revision ID: 20260503_0018
Revises: 20260503_0017
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260503_0018"
down_revision: str | None = "20260503_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in ("news_events", "alerts"):
        op.add_column(table_name, sa.Column("title_original", sa.Text(), nullable=True))
        op.add_column(table_name, sa.Column("summary_original", sa.Text(), nullable=True))
        op.add_column(table_name, sa.Column("title_zh", sa.Text(), nullable=True))
        op.add_column(table_name, sa.Column("summary_zh", sa.Text(), nullable=True))
        op.add_column(
            table_name,
            sa.Column(
                "source_language",
                sa.String(length=12),
                server_default="unknown",
                nullable=False,
            ),
        )
        op.add_column(
            table_name,
            sa.Column(
                "translation_status",
                sa.String(length=20),
                server_default="pending",
                nullable=False,
            ),
        )
        op.add_column(table_name, sa.Column("translation_model", sa.String(length=100), nullable=True))
        op.add_column(
            table_name,
            sa.Column("translation_prompt_version", sa.String(length=60), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("translation_glossary_version", sa.String(length=60), nullable=True),
        )
        op.add_column(table_name, sa.Column("translated_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index(
            f"ix_{table_name}_translation_status",
            table_name,
            ["translation_status"],
        )

    op.execute("UPDATE news_events SET title_original = title WHERE title_original IS NULL")
    op.execute("UPDATE news_events SET summary_original = summary WHERE summary_original IS NULL")
    op.execute("UPDATE alerts SET title_original = title WHERE title_original IS NULL")
    op.execute("UPDATE alerts SET summary_original = summary WHERE summary_original IS NULL")


def downgrade() -> None:
    for table_name in ("alerts", "news_events"):
        op.drop_index(f"ix_{table_name}_translation_status", table_name=table_name)
        op.drop_column(table_name, "translated_at")
        op.drop_column(table_name, "translation_glossary_version")
        op.drop_column(table_name, "translation_prompt_version")
        op.drop_column(table_name, "translation_model")
        op.drop_column(table_name, "translation_status")
        op.drop_column(table_name, "source_language")
        op.drop_column(table_name, "summary_zh")
        op.drop_column(table_name, "title_zh")
        op.drop_column(table_name, "summary_original")
        op.drop_column(table_name, "title_original")
