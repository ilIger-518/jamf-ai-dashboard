"""add dashboard logs table

Revision ID: f3a1b2c4d5e6
Revises: e5a7c9d1b2f4
Create Date: 2026-03-16 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f3a1b2c4d5e6"
down_revision: str | None = "e5a7c9d1b2f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dashboard_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("level", sa.String(16), nullable=False, server_default="info"),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("method", sa.String(12), nullable=True),
        sa.Column("path", sa.String(255), nullable=True),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("details", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_dashboard_logs_category", "dashboard_logs", ["category"])
    op.create_index("ix_dashboard_logs_action", "dashboard_logs", ["action"])
    op.create_index("ix_dashboard_logs_user_id", "dashboard_logs", ["user_id"])
    op.create_index("ix_dashboard_logs_username", "dashboard_logs", ["username"])
    op.create_index("ix_dashboard_logs_created_at", "dashboard_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_dashboard_logs_created_at", "dashboard_logs")
    op.drop_index("ix_dashboard_logs_username", "dashboard_logs")
    op.drop_index("ix_dashboard_logs_user_id", "dashboard_logs")
    op.drop_index("ix_dashboard_logs_action", "dashboard_logs")
    op.drop_index("ix_dashboard_logs_category", "dashboard_logs")
    op.drop_table("dashboard_logs")
