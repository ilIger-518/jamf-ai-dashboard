"""KnowledgeDocument model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[str] = mapped_column(String(1024), nullable=False)  # URL or file path
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SHA-256 hash of the source file — used to skip re-ingestion if unchanged
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)  # "pdf" | "markdown" | "url"
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # ChromaDB collection this document's chunks belong to
    collection_name: Mapped[str] = mapped_column(String(128), default="jamf_docs", nullable=False)

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
