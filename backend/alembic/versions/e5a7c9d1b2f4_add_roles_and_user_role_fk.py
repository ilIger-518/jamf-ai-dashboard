"""add roles and user role fk

Revision ID: e5a7c9d1b2f4
Revises: d9e4a1b7c2f3
Create Date: 2026-03-13 14:10:00.000000

"""

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e5a7c9d1b2f4"
down_revision: str | None = "d9e4a1b7c2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ADMIN_ROLE_ID = uuid.UUID("6a925f66-dcfc-4c3b-8a4e-88c6904e2d34")
VIEWER_ROLE_ID = uuid.UUID("deeb16d0-b8ad-45d0-a01f-631f923ce1d1")

ADMIN_PERMISSIONS = [
    "servers.read",
    "servers.manage",
    "servers.sync",
    "knowledge.read",
    "knowledge.manage",
    "migrator.manage",
    "users.manage",
    "roles.manage",
    "settings.manage",
]
VIEWER_PERMISSIONS = [
    "servers.read",
    "knowledge.read",
    "settings.manage",
]


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("permissions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_roles_name"), "roles", ["name"], unique=True)

    op.add_column("users", sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_users_role_id"), "users", ["role_id"], unique=False)
    op.create_foreign_key("fk_users_role_id_roles", "users", "roles", ["role_id"], ["id"], ondelete="SET NULL")

    roles_table = sa.table(
        "roles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("permissions", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("is_system", sa.Boolean()),
    )
    users_table = sa.table(
        "users",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("is_admin", sa.Boolean()),
        sa.column("role_id", postgresql.UUID(as_uuid=True)),
    )

    op.bulk_insert(
        roles_table,
        [
            {
                "id": ADMIN_ROLE_ID,
                "name": "Administrator",
                "description": "Full access to all application management features.",
                "permissions": ADMIN_PERMISSIONS,
                "is_system": True,
            },
            {
                "id": VIEWER_ROLE_ID,
                "name": "Viewer",
                "description": "Read-only application access.",
                "permissions": VIEWER_PERMISSIONS,
                "is_system": True,
            },
        ],
    )

    connection = op.get_bind()
    connection.execute(users_table.update().where(users_table.c.is_admin.is_(True)).values(role_id=ADMIN_ROLE_ID))
    connection.execute(users_table.update().where(users_table.c.is_admin.is_(False)).values(role_id=VIEWER_ROLE_ID))


def downgrade() -> None:
    op.drop_constraint("fk_users_role_id_roles", "users", type_="foreignkey")
    op.drop_index(op.f("ix_users_role_id"), table_name="users")
    op.drop_column("users", "role_id")
    op.drop_index(op.f("ix_roles_name"), table_name="roles")
    op.drop_table("roles")
