"""add management_id to devices

Revision ID: c1d2e3f4a5b6
Revises: 7f6e5d4c3b2a
Create Date: 2026-04-08 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "7f6e5d4c3b2a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    tables = inspector.get_table_names()
    if "devices" in tables:
        device_columns = {col["name"] for col in inspector.get_columns("devices")}
        if "management_id" not in device_columns:
            op.add_column("devices", sa.Column("management_id", sa.String(length=64), nullable=True))

        device_indexes = {idx["name"] for idx in inspector.get_indexes("devices")}
        if "ix_devices_management_id" not in device_indexes and "management_id" in {
            col["name"] for col in inspector.get_columns("devices")
        }:
            op.create_index("ix_devices_management_id", "devices", ["management_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_devices_management_id", table_name="devices")
    op.drop_column("devices", "management_id")
