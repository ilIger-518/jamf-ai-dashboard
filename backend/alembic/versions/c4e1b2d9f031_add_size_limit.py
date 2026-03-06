"""add max_size_mb and bytes_scraped to scrape_jobs

Revision ID: c4e1b2d9f031
Revises: b3f2a1c8d905
Create Date: 2026-03-06 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4e1b2d9f031'
down_revision: Union[str, None] = 'b3f2a1c8d905'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make max_pages nullable (None = unlimited)
    op.alter_column('scrape_jobs', 'max_pages', nullable=True)
    # Add size limit and bytes-scraped tracking columns
    op.add_column('scrape_jobs', sa.Column('max_size_mb', sa.Integer(), nullable=True))
    op.add_column('scrape_jobs', sa.Column('bytes_scraped', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('scrape_jobs', 'bytes_scraped')
    op.drop_column('scrape_jobs', 'max_size_mb')
    op.alter_column('scrape_jobs', 'max_pages', nullable=False)
