"""PatchTitle model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PatchTitle(Base):
    __tablename__ = "patch_titles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    jamf_id: Mapped[int] = mapped_column(Integer, nullable=False)
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jamf_servers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    software_title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    current_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latest_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    patched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unpatched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    server: Mapped["JamfServer"] = relationship("JamfServer", back_populates="patch_titles")  # noqa: F821
