"""add scrape job logs table

Revision ID: d9e4a1b7c2f3
Revises: 1c7a8d2e4b55
Create Date: 2026-03-13 13:35:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d9e4a1b7c2f3"
down_revision: str | None = "1c7a8d2e4b55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "scrape_job_logs" not in existing_tables:
        op.create_table(
            "scrape_job_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("level", sa.String(length=16), nullable=False, server_default="info"),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["job_id"], ["scrape_jobs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    existing_indexes = (
        {idx["name"] for idx in inspector.get_indexes("scrape_job_logs")}
        if "scrape_job_logs" in inspector.get_table_names()
        else set()
    )
    if op.f("ix_scrape_job_logs_job_id") not in existing_indexes:
        op.create_index(op.f("ix_scrape_job_logs_job_id"), "scrape_job_logs", ["job_id"], unique=False)
    if op.f("ix_scrape_job_logs_created_at") not in existing_indexes:
        op.create_index(op.f("ix_scrape_job_logs_created_at"), "scrape_job_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_scrape_job_logs_created_at"), table_name="scrape_job_logs")
    op.drop_index(op.f("ix_scrape_job_logs_job_id"), table_name="scrape_job_logs")
    op.drop_table("scrape_job_logs")
