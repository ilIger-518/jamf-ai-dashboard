"""merge scrape controls and entity table branches

Revision ID: 9b1d4e7a2c11
Revises: b2c3d4e5f6a7, f2c6d1a9b8e0
Create Date: 2026-03-13 10:45:00.000000

"""

from collections.abc import Sequence

revision: str = "9b1d4e7a2c11"
down_revision: str | Sequence[str] | None = ("b2c3d4e5f6a7", "f2c6d1a9b8e0")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
