"""DashboardLog model for server/login/action audit events."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DashboardLog(Base):
    __tablename__ = "dashboard_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True
    )  # server|login|action
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False, server_default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)

    method: Mapped[object] = mapped_column(String(12), nullable=True)
    path: Mapped[object] = mapped_column(String(255), nullable=True)
    status_code: Mapped[object] = mapped_column(Integer, nullable=True)

    user_id: Mapped[object] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    username: Mapped[object] = mapped_column(String(64), nullable=True, index=True)
    ip_address: Mapped[object] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[object] = mapped_column(String(255), nullable=True)
    details: Mapped[object] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
