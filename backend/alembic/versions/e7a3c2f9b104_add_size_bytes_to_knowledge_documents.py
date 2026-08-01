"""add size_bytes to knowledge_documents

Revision ID: e7a3c2f9b104
Revises: c4e1b2d9f031
Create Date: 2026-03-06 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e7a3c2f9b104"
down_revision: str | None = "c4e1b2d9f031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "knowledge_documents" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("knowledge_documents")}
    if "size_bytes" not in columns:
        op.add_column(
            "knowledge_documents",
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    op.drop_column("knowledge_documents", "size_bytes")
