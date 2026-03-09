"""add policies table

Revision ID: a1f2b3c4d5e6
Revises: e7a3c2f9b104
Create Date: 2026-03-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1f2b3c4d5e6"
down_revision: str | None = "e7a3c2f9b104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "policies" not in existing_tables:
        op.create_table(
            "policies",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("jamf_id", sa.Integer(), nullable=False),
            sa.Column(
                "server_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("jamf_servers.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("category", sa.String(length=128), nullable=True),
            sa.Column("trigger", sa.String(length=64), nullable=True),
            sa.Column("scope_description", sa.Text(), nullable=True),
            sa.Column("payload_description", sa.Text(), nullable=True),
            sa.Column(
                "synced_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("policies")} if "policies" in existing_tables else set()

    if "ix_policies_server_id" not in existing_indexes:
        op.create_index("ix_policies_server_id", "policies", ["server_id"], unique=False)
    if "ix_policies_name" not in existing_indexes:
        op.create_index("ix_policies_name", "policies", ["name"], unique=False)
    if "ix_policies_category" not in existing_indexes:
        op.create_index("ix_policies_category", "policies", ["category"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_policies_category", table_name="policies")
    op.drop_index("ix_policies_name", table_name="policies")
    op.drop_index("ix_policies_server_id", table_name="policies")
    op.drop_table("policies")
