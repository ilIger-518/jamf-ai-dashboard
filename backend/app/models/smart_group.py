"""SmartGroup model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SmartGroup(Base):
    __tablename__ = "smart_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jamf_id: Mapped[int] = mapped_column(Integer, nullable=False)
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jamf_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # JSON list of criterion dicts: [{name, priority, and_or, search_type, value}, ...]
    criteria: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    member_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_refreshed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    server: Mapped["JamfServer"] = relationship("JamfServer", back_populates="smart_groups")  # noqa: F821
