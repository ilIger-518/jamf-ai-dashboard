"""Add unique constraints on (jamf_id, server_id) to synced entity tables.

Deduplicates any existing rows (keeps the one with the latest synced_at,
ties broken by row id) before adding the constraint so the migration is
safe to run on a populated database.

Revision ID: d1e2f3a4b5c6
Revises: 1c7a8d2e4b55
Create Date: 2026-04-09 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "1c7a8d2e4b55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = [
    ("devices", "uq_devices_jamf_id_server_id"),
    ("policies", "uq_policies_jamf_id_server_id"),
    ("smart_groups", "uq_smart_groups_jamf_id_server_id"),
    ("patch_titles", "uq_patch_titles_jamf_id_server_id"),
]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    for table_name, constraint_name in _TABLES:
        if table_name not in existing_tables:
            continue

        # Check if constraint already exists (idempotent migration).
        existing_uqs = {uq["name"] for uq in inspector.get_unique_constraints(table_name)}
        if constraint_name in existing_uqs:
            continue

        # Remove duplicate rows, keeping the one with the latest synced_at.
        # Ties in synced_at are broken by the string representation of id so
        # the result is deterministic without relying on ctid.
        conn.execute(
            sa.text(
                f"""
                DELETE FROM {table_name}
                WHERE id IN (
                    SELECT id FROM (
                        SELECT id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY jamf_id, server_id
                                   ORDER BY synced_at DESC, id::text
                               ) AS rn
                        FROM {table_name}
                    ) ranked
                    WHERE rn > 1
                )
                """
            )
        )

        op.create_unique_constraint(
            constraint_name,
            table_name,
            ["jamf_id", "server_id"],
        )


def downgrade() -> None:
    for table_name, constraint_name in reversed(_TABLES):
        try:
            op.drop_constraint(constraint_name, table_name, type_="unique")
        except Exception:  # noqa: BLE001
            pass
