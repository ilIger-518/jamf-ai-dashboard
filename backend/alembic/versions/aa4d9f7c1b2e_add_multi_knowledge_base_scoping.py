"""add multi knowledge base scoping

Revision ID: aa4d9f7c1b2e
Revises: 9c8b7a6d5e4f
Create Date: 2026-03-27 11:45:00.000000

"""

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "aa4d9f7c1b2e"
down_revision: str | None = "9c8b7a6d5e4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "knowledge_bases" not in tables:
        op.create_table(
            "knowledge_bases",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("collection_name", sa.String(length=128), nullable=False),
            sa.Column("embedding_provider", sa.String(length=16), nullable=True),
            sa.Column("embedding_model", sa.String(length=255), nullable=True),
            sa.Column("embedding_dimension", sa.Integer(), nullable=True),
            sa.Column("dimension_tag", sa.String(length=64), nullable=True),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name", name="uq_knowledge_bases_name"),
            sa.UniqueConstraint("collection_name", name="uq_knowledge_bases_collection_name"),
        )
        op.create_index("ix_knowledge_bases_name", "knowledge_bases", ["name"], unique=True)
        tables.add("knowledge_bases")
    else:
        kb_columns = {col["name"] for col in inspector.get_columns("knowledge_bases")}
        if "dimension_tag" not in kb_columns:
            op.add_column("knowledge_bases", sa.Column("dimension_tag", sa.String(length=64), nullable=True))

    default_kb_id: uuid.UUID
    default_row = conn.execute(
        sa.text(
            "SELECT id FROM knowledge_bases WHERE is_default = true ORDER BY created_at ASC LIMIT 1"
        )
    ).fetchone()

    if default_row and default_row[0]:
        default_kb_id = default_row[0]
    else:
        existing_row = conn.execute(
            sa.text("SELECT id FROM knowledge_bases ORDER BY created_at ASC LIMIT 1")
        ).fetchone()
        if existing_row and existing_row[0]:
            default_kb_id = existing_row[0]
            conn.execute(sa.text("UPDATE knowledge_bases SET is_default = false"))
            conn.execute(
                sa.text("UPDATE knowledge_bases SET is_default = true WHERE id = :kb_id"),
                {"kb_id": default_kb_id},
            )
        else:
            default_kb_id = uuid.uuid4()
            conn.execute(
                sa.text(
                    """
                    INSERT INTO knowledge_bases (
                        id,
                        name,
                        description,
                        collection_name,
                        embedding_provider,
                        embedding_model,
                        embedding_dimension,
                        dimension_tag,
                        is_default
                    ) VALUES (
                        :id,
                        :name,
                        :description,
                        :collection_name,
                        :embedding_provider,
                        :embedding_model,
                        :embedding_dimension,
                        :dimension_tag,
                        true
                    )
                    """
                ),
                {
                    "id": default_kb_id,
                    "name": "Default Knowledge Base",
                    "description": "Auto-created default knowledge base",
                    "collection_name": "jamf_knowledge",
                    "embedding_provider": None,
                    "embedding_model": None,
                    "embedding_dimension": None,
                    "dimension_tag": "legacy",
                },
            )

    if "scrape_jobs" in tables:
        scrape_columns = {col["name"] for col in inspector.get_columns("scrape_jobs")}
        if "knowledge_base_id" not in scrape_columns:
            op.add_column(
                "scrape_jobs",
                sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=True),
            )
        scrape_indexes = {idx["name"] for idx in inspector.get_indexes("scrape_jobs")}
        if "ix_scrape_jobs_knowledge_base_id" not in scrape_indexes:
            op.create_index("ix_scrape_jobs_knowledge_base_id", "scrape_jobs", ["knowledge_base_id"], unique=False)
        conn.execute(
            sa.text(
                "UPDATE scrape_jobs SET knowledge_base_id = :kb_id WHERE knowledge_base_id IS NULL"
            ),
            {"kb_id": default_kb_id},
        )

    if "knowledge_documents" in tables:
        doc_columns = {col["name"] for col in inspector.get_columns("knowledge_documents")}
        if "knowledge_base_id" not in doc_columns:
            op.add_column(
                "knowledge_documents",
                sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=True),
            )
        doc_indexes = {idx["name"] for idx in inspector.get_indexes("knowledge_documents")}
        if "ix_knowledge_documents_knowledge_base_id" not in doc_indexes:
            op.create_index(
                "ix_knowledge_documents_knowledge_base_id",
                "knowledge_documents",
                ["knowledge_base_id"],
                unique=False,
            )
        conn.execute(
            sa.text(
                "UPDATE knowledge_documents SET knowledge_base_id = :kb_id WHERE knowledge_base_id IS NULL"
            ),
            {"kb_id": default_kb_id},
        )


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for this schema-alignment migration.")
