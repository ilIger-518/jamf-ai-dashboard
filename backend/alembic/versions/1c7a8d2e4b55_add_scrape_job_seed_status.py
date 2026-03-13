"""add scrape job seed status fields

Revision ID: 1c7a8d2e4b55
Revises: 9b1d4e7a2c11
Create Date: 2026-03-13 11:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "1c7a8d2e4b55"
down_revision: str | None = "9b1d4e7a2c11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scrape_jobs",
        sa.Column("seed_mode", sa.String(length=16), nullable=False, server_default="start_url"),
    )
    op.add_column(
        "scrape_jobs",
        sa.Column("seed_urls", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "scrape_jobs",
        sa.Column("sitemap_timed_out", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("scrape_jobs", "sitemap_timed_out")
    op.drop_column("scrape_jobs", "seed_urls")
    op.drop_column("scrape_jobs", "seed_mode")
