"""ScrapeJob model — tracks a background web-scrape/ingest job."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    domain: Mapped[str] = mapped_column(String(1024), nullable=False)
    max_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = unlimited
    max_size_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = no size limit
    topic_filter: Mapped[str | None] = mapped_column(Text, nullable=True)

    # "pending" | "running" | "completed" | "completed_with_errors" | "failed"
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)

    pages_scraped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pages_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_scraped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Runtime controls
    pause_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # CPU cap control: "total" (1-100) or "core" (1..cores*100, Linux-style)
    cpu_cap_mode: Mapped[str] = mapped_column(String(16), default="total", nullable=False)
    cpu_cap_percent: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    seed_mode: Mapped[str] = mapped_column(String(16), default="start_url", nullable=False)
    seed_urls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sitemap_timed_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    continued_from_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    last_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
