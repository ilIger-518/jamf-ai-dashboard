"""add scrape_jobs table

Revision ID: b3f2a1c8d905
Revises: 01ee4908be42
Create Date: 2026-03-05 20:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3f2a1c8d905'
down_revision: str | None = '01ee4908be42'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'scrape_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('domain', sa.String(length=1024), nullable=False),
        sa.Column('max_pages', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('topic_filter', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('pages_scraped', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pages_found', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_scrape_jobs_status', 'scrape_jobs', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_scrape_jobs_status', table_name='scrape_jobs')
    op.drop_table('scrape_jobs')
