"""add sources column to chat_messages

Revision ID: b6d2f9a1c4e8
Revises: aa4d9f7c1b2e
Create Date: 2026-03-27 13:25:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b6d2f9a1c4e8"
down_revision: str | None = "aa4d9f7c1b2e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    if "chat_messages" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("chat_messages")}
    if "sources" not in columns:
        op.add_column(
            "chat_messages",
            sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    if "chat_messages" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("chat_messages")}
    if "sources" in columns:
        op.drop_column("chat_messages", "sources")
