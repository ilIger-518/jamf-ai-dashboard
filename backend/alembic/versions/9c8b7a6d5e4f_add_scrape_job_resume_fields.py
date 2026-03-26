"""add scrape job resume fields

Revision ID: 9c8b7a6d5e4f
Revises: 8a7b6c5d4e3f
Create Date: 2026-03-26 15:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "9c8b7a6d5e4f"
down_revision: str | None = "8a7b6c5d4e3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "scrape_jobs" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("scrape_jobs")}

    if "continued_from_job_id" not in columns:
        op.add_column("scrape_jobs", sa.Column("continued_from_job_id", postgresql.UUID(as_uuid=True), nullable=True))
    if "last_url" not in columns:
        op.add_column("scrape_jobs", sa.Column("last_url", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for this schema-alignment migration.")
