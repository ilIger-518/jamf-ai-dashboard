"""add runtime controls to scrape_jobs

Revision ID: f2c6d1a9b8e0
Revises: e7a3c2f9b104
Create Date: 2026-03-13 10:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2c6d1a9b8e0"
down_revision: str | None = "e7a3c2f9b104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scrape_jobs",
        sa.Column("pause_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "scrape_jobs",
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "scrape_jobs",
        sa.Column("cpu_cap_mode", sa.String(length=16), nullable=False, server_default="total"),
    )
    op.add_column(
        "scrape_jobs",
        sa.Column("cpu_cap_percent", sa.Integer(), nullable=False, server_default="100"),
    )


def downgrade() -> None:
    op.drop_column("scrape_jobs", "cpu_cap_percent")
    op.drop_column("scrape_jobs", "cpu_cap_mode")
    op.drop_column("scrape_jobs", "cancel_requested")
    op.drop_column("scrape_jobs", "pause_requested")
