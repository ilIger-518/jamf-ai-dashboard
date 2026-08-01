"""align dashboard logs and devices schema

Revision ID: 7f6e5d4c3b2a
Revises: f3a1b2c4d5e6
Create Date: 2026-03-25 15:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "7f6e5d4c3b2a"
down_revision: str | None = "f3a1b2c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    tables = inspector.get_table_names()

    if "dashboard_logs" in tables:
        dashboard_columns = {col["name"]: col for col in inspector.get_columns("dashboard_logs")}

        if "user_id" in dashboard_columns and not dashboard_columns["user_id"]["nullable"]:
            op.alter_column(
                "dashboard_logs",
                "user_id",
                existing_type=postgresql.UUID(as_uuid=True),
                nullable=True,
            )

        if "resource_type" in dashboard_columns:
            conn.execute(
                sa.text(
                    "UPDATE dashboard_logs SET resource_type = category WHERE resource_type IS NULL"
                )
            )
            op.alter_column(
                "dashboard_logs",
                "resource_type",
                existing_type=sa.String(length=255),
                nullable=True,
            )

    if "devices" in tables:
        device_columns = {col["name"] for col in inspector.get_columns("devices")}

        missing_columns: list[sa.Column] = []
        if "udid" not in device_columns:
            missing_columns.append(sa.Column("udid", sa.String(length=64), nullable=True))
        if "asset_tag" not in device_columns:
            missing_columns.append(sa.Column("asset_tag", sa.String(length=128), nullable=True))
        if "model_identifier" not in device_columns:
            missing_columns.append(
                sa.Column("model_identifier", sa.String(length=64), nullable=True)
            )
        if "processor" not in device_columns:
            missing_columns.append(sa.Column("processor", sa.String(length=128), nullable=True))
        if "ram_mb" not in device_columns:
            missing_columns.append(sa.Column("ram_mb", sa.Integer(), nullable=True))
        if "os_build" not in device_columns:
            missing_columns.append(sa.Column("os_build", sa.String(length=16), nullable=True))
        if "is_managed" not in device_columns:
            missing_columns.append(
                sa.Column(
                    "is_managed", sa.Boolean(), nullable=False, server_default=sa.text("false")
                )
            )
        if "is_supervised" not in device_columns:
            missing_columns.append(
                sa.Column(
                    "is_supervised", sa.Boolean(), nullable=False, server_default=sa.text("false")
                )
            )
        if "last_contact" not in device_columns:
            missing_columns.append(
                sa.Column("last_contact", sa.DateTime(timezone=True), nullable=True)
            )
        if "last_enrollment" not in device_columns:
            missing_columns.append(
                sa.Column("last_enrollment", sa.DateTime(timezone=True), nullable=True)
            )
        if "username" not in device_columns:
            missing_columns.append(sa.Column("username", sa.String(length=128), nullable=True))
        if "full_name" not in device_columns:
            missing_columns.append(sa.Column("full_name", sa.String(length=255), nullable=True))
        if "email" not in device_columns:
            missing_columns.append(sa.Column("email", sa.String(length=255), nullable=True))
        if "department" not in device_columns:
            missing_columns.append(sa.Column("department", sa.String(length=128), nullable=True))
        if "building" not in device_columns:
            missing_columns.append(sa.Column("building", sa.String(length=128), nullable=True))
        if "site" not in device_columns:
            missing_columns.append(sa.Column("site", sa.String(length=128), nullable=True))
        if "synced_at" not in device_columns:
            missing_columns.append(
                sa.Column(
                    "synced_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.func.now(),
                )
            )

        for column in missing_columns:
            op.add_column("devices", column)

        device_indexes = {idx["name"] for idx in inspector.get_indexes("devices")}
        if "ix_devices_udid" not in device_indexes and "udid" in {
            col["name"] for col in inspector.get_columns("devices")
        }:
            op.create_index("ix_devices_udid", "devices", ["udid"], unique=False)
        if "ix_devices_name" not in device_indexes:
            op.create_index("ix_devices_name", "devices", ["name"], unique=False)
        if "ix_devices_serial_number" not in device_indexes and "serial_number" in {
            col["name"] for col in inspector.get_columns("devices")
        }:
            op.create_index("ix_devices_serial_number", "devices", ["serial_number"], unique=False)
        if "ix_devices_os_version" not in device_indexes and "os_version" in {
            col["name"] for col in inspector.get_columns("devices")
        }:
            op.create_index("ix_devices_os_version", "devices", ["os_version"], unique=False)
        if "ix_devices_last_contact" not in device_indexes and "last_contact" in {
            col["name"] for col in inspector.get_columns("devices")
        }:
            op.create_index("ix_devices_last_contact", "devices", ["last_contact"], unique=False)
        if "ix_devices_username" not in device_indexes and "username" in {
            col["name"] for col in inspector.get_columns("devices")
        }:
            op.create_index("ix_devices_username", "devices", ["username"], unique=False)


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for this schema-alignment migration.")
