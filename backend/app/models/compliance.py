"""ComplianceResult and SecurityStatus models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ComplianceResult(Base):
    __tablename__ = "compliance_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    check_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # "pass" | "fail" | "warn"
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    device: Mapped["Device"] = relationship("Device", back_populates="compliance_results")  # noqa: F821


class SecurityStatus(Base):
    __tablename__ = "security_statuses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    firewall_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sip_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    gatekeeper_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    filevault_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    remote_login_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    disk_encryption_status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    device: Mapped["Device"] = relationship("Device", back_populates="security_status")  # noqa: F821
