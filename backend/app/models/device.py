"""Device, DeviceApplication, and DevicePolicy models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Jamf-side integer ID — combined with server_id gives a unique key
    jamf_id: Mapped[int] = mapped_column(Integer, nullable=False)
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jamf_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identity
    udid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    serial_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    asset_tag: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Hardware
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_identifier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ram_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # OS
    os_version: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    os_build: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Management
    is_managed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_supervised: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_contact: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_enrollment: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Organisational
    username: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    building: Mapped[str | None] = mapped_column(String(128), nullable=True)
    site: Mapped[str | None] = mapped_column(String(128), nullable=True)

    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # relationships
    server: Mapped["JamfServer"] = relationship("JamfServer", back_populates="devices")  # noqa: F821
    applications: Mapped[list["DeviceApplication"]] = relationship(
        "DeviceApplication", back_populates="device", cascade="all, delete-orphan"
    )
    policy_history: Mapped[list["DevicePolicy"]] = relationship(
        "DevicePolicy", back_populates="device", cascade="all, delete-orphan"
    )
    compliance_results: Mapped[list["ComplianceResult"]] = relationship(  # noqa: F821
        "ComplianceResult", back_populates="device", cascade="all, delete-orphan"
    )
    security_status: Mapped["SecurityStatus | None"] = relationship(  # noqa: F821
        "SecurityStatus", back_populates="device", uselist=False, cascade="all, delete-orphan"
    )


class DeviceApplication(Base):
    __tablename__ = "device_applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    short_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bundle_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    device: Mapped["Device"] = relationship("Device", back_populates="applications")


class DevicePolicy(Base):
    """Records when a policy was last run on a device and whether it succeeded."""

    __tablename__ = "device_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    last_executed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # "success" | "failed" | "pending"

    device: Mapped["Device"] = relationship("Device", back_populates="policy_history")
    policy: Mapped["Policy"] = relationship("Policy")  # noqa: F821
