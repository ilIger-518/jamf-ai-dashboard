"""JamfServer model — one row per connected Jamf Pro instance."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class JamfServer(Base):
    __tablename__ = "jamf_servers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(String(512), nullable=False)

    # Encrypted at rest via Fernet — see services/encryption.py
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    client_secret: Mapped[str] = mapped_column(Text, nullable=False)

    # Dedicated read-only credentials used exclusively by the AI module
    ai_client_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_client_secret: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # relationships
    devices: Mapped[list["Device"]] = relationship(  # noqa: F821
        "Device", back_populates="server", cascade="all, delete-orphan"
    )
    policies: Mapped[list["Policy"]] = relationship(  # noqa: F821
        "Policy", back_populates="server", cascade="all, delete-orphan"
    )
    smart_groups: Mapped[list["SmartGroup"]] = relationship(  # noqa: F821
        "SmartGroup", back_populates="server", cascade="all, delete-orphan"
    )
    patch_titles: Mapped[list["PatchTitle"]] = relationship(  # noqa: F821
        "PatchTitle", back_populates="server", cascade="all, delete-orphan"
    )
