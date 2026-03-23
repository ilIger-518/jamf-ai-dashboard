"""add smart_groups and patch_titles tables

Revision ID: b2c3d4e5f6a7
Revises: a1f2b3c4d5e6
Create Date: 2026-03-09 00:01:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1f2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # ── smart_groups ────────────────────────────────────────────────────────
    if "smart_groups" not in existing_tables:
        op.create_table(
            "smart_groups",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("jamf_id", sa.Integer(), nullable=False),
            sa.Column(
                "server_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("jamf_servers.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_refreshed", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "synced_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if "smart_groups" in inspector.get_table_names():
        sg_columns = {col["name"] for col in inspector.get_columns("smart_groups")}
        if "criteria" not in sg_columns:
            op.add_column(
                "smart_groups",
                sa.Column("criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            )
        if "member_count" not in sg_columns:
            op.add_column(
                "smart_groups",
                sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
            )
        if "last_refreshed" not in sg_columns:
            op.add_column(
                "smart_groups",
                sa.Column("last_refreshed", sa.DateTime(timezone=True), nullable=True),
            )
        if "synced_at" not in sg_columns:
            op.add_column(
                "smart_groups",
                sa.Column(
                    "synced_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.text("now()"),
                    nullable=False,
                ),
            )

    sg_columns = (
        {col["name"] for col in inspector.get_columns("smart_groups")}
        if "smart_groups" in inspector.get_table_names()
        else set()
    )
    sg_indexes = (
        {idx["name"] for idx in inspector.get_indexes("smart_groups")}
        if "smart_groups" in inspector.get_table_names()
        else set()
    )
    if "ix_smart_groups_server_id" not in sg_indexes and "server_id" in sg_columns:
        op.create_index("ix_smart_groups_server_id", "smart_groups", ["server_id"], unique=False)
    if "ix_smart_groups_name" not in sg_indexes and "name" in sg_columns:
        op.create_index("ix_smart_groups_name", "smart_groups", ["name"], unique=False)

    # ── patch_titles ────────────────────────────────────────────────────────
    if "patch_titles" not in existing_tables:
        op.create_table(
            "patch_titles",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("jamf_id", sa.Integer(), nullable=False),
            sa.Column(
                "server_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("jamf_servers.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("software_title", sa.String(length=255), nullable=False),
            sa.Column("current_version", sa.String(length=64), nullable=True),
            sa.Column("latest_version", sa.String(length=64), nullable=True),
            sa.Column("patched_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("unpatched_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "synced_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if "patch_titles" in inspector.get_table_names():
        pt_columns = {col["name"] for col in inspector.get_columns("patch_titles")}
        if "software_title" not in pt_columns:
            op.add_column(
                "patch_titles",
                sa.Column("software_title", sa.String(length=255), nullable=True),
            )
        if "current_version" not in pt_columns:
            op.add_column(
                "patch_titles",
                sa.Column("current_version", sa.String(length=64), nullable=True),
            )
        if "latest_version" not in pt_columns:
            op.add_column(
                "patch_titles",
                sa.Column("latest_version", sa.String(length=64), nullable=True),
            )
        if "patched_count" not in pt_columns:
            op.add_column(
                "patch_titles",
                sa.Column("patched_count", sa.Integer(), nullable=False, server_default="0"),
            )
        if "unpatched_count" not in pt_columns:
            op.add_column(
                "patch_titles",
                sa.Column("unpatched_count", sa.Integer(), nullable=False, server_default="0"),
            )
        if "synced_at" not in pt_columns:
            op.add_column(
                "patch_titles",
                sa.Column(
                    "synced_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.text("now()"),
                    nullable=False,
                ),
            )

    pt_columns = (
        {col["name"] for col in inspector.get_columns("patch_titles")}
        if "patch_titles" in inspector.get_table_names()
        else set()
    )
    pt_indexes = (
        {idx["name"] for idx in inspector.get_indexes("patch_titles")}
        if "patch_titles" in inspector.get_table_names()
        else set()
    )
    if "ix_patch_titles_server_id" not in pt_indexes and "server_id" in pt_columns:
        op.create_index("ix_patch_titles_server_id", "patch_titles", ["server_id"], unique=False)
    if "ix_patch_titles_software_title" not in pt_indexes and "software_title" in pt_columns:
        op.create_index("ix_patch_titles_software_title", "patch_titles", ["software_title"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_patch_titles_software_title", table_name="patch_titles")
    op.drop_index("ix_patch_titles_server_id", table_name="patch_titles")
    op.drop_table("patch_titles")
    op.drop_index("ix_smart_groups_name", table_name="smart_groups")
    op.drop_index("ix_smart_groups_server_id", table_name="smart_groups")
    op.drop_table("smart_groups")
