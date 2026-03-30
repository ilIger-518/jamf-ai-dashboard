"""align patch titles schema

Revision ID: 8a7b6c5d4e3f
Revises: 7f6e5d4c3b2a
Create Date: 2026-03-26 14:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8a7b6c5d4e3f"
down_revision: str | None = "7f6e5d4c3b2a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "patch_titles" not in inspector.get_table_names():
        return

    columns = {col["name"]: col for col in inspector.get_columns("patch_titles")}

    if "name" in columns:
        conn.execute(sa.text("UPDATE patch_titles SET name = software_title WHERE name IS NULL"))
        if not columns["name"]["nullable"]:
            op.alter_column(
                "patch_titles", "name", existing_type=sa.String(length=255), nullable=True
            )


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for this schema-alignment migration.")
