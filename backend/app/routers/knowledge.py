"""Knowledge base router — manage scrape jobs and stored knowledge sources."""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.dependencies import AdminUser, CurrentUser
from app.models.knowledge import KnowledgeDocument
from app.models.scrape_job import ScrapeJob
from app.services.scraper import run_scrape_job
from app.services.vector_store import delete_by_source

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ── Request / Response schemas ────────────────────────────────────────────────


class ScrapeRequest(BaseModel):
    domain: str
    max_pages: int | None = 100  # None = unlimited
    max_size_mb: int | None = None  # e.g. 500 to stop after 500 MB of content
    topic_filter: str | None = None  # e.g. "patch management" or "MDM enrollment"


class ScrapeJobResponse(BaseModel):
    id: str
    domain: str
    max_pages: int | None
    max_size_mb: int | None
    topic_filter: str | None
    status: str
    pages_scraped: int
    pages_found: int
    bytes_scraped: int
    error: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None

    @classmethod
    def from_orm(cls, job: ScrapeJob) -> "ScrapeJobResponse":
        return cls(
            id=str(job.id),
            domain=job.domain,
            max_pages=job.max_pages,
            max_size_mb=job.max_size_mb,
            topic_filter=job.topic_filter,
            status=job.status,
            pages_scraped=job.pages_scraped,
            pages_found=job.pages_found,
            bytes_scraped=job.bytes_scraped,
            error=job.error,
            created_at=job.created_at.isoformat(),
            started_at=job.started_at.isoformat() if job.started_at else None,
            finished_at=job.finished_at.isoformat() if job.finished_at else None,
        )


class SourceResponse(BaseModel):
    id: str
    title: str
    source: str
    doc_type: str
    chunk_count: int
    size_bytes: int
    ingested_at: str

    @classmethod
    def from_orm(cls, doc: KnowledgeDocument) -> "SourceResponse":
        return cls(
            id=str(doc.id),
            title=doc.title,
            source=doc.source,
            doc_type=doc.doc_type,
            chunk_count=doc.chunk_count,
            size_bytes=doc.size_bytes,
            ingested_at=doc.ingested_at.isoformat(),
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/scrape", response_model=ScrapeJobResponse, status_code=202)
async def start_scrape(
    body: ScrapeRequest,
    background_tasks: BackgroundTasks,
    _: AdminUser,
) -> ScrapeJobResponse:
    """Start a background scrape job for a domain. Admin only."""
    # Basic URL normalisation — ensure it starts with http
    domain = body.domain.strip()
    if not domain.startswith("http"):
        domain = "https://" + domain

    async with AsyncSessionLocal() as session:
        job = ScrapeJob(
            domain=domain,
            max_pages=body.max_pages,  # None = unlimited
            max_size_mb=body.max_size_mb,
            topic_filter=body.topic_filter or None,
            status="pending",
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = str(job.id)

    background_tasks.add_task(_run_job_safe, job_id)
    return ScrapeJobResponse.from_orm(job)


async def _run_job_safe(job_id: str) -> None:
    """Wrapper that catches unhandled exceptions and marks job as failed."""
    try:
        await run_scrape_job(job_id)
    except Exception as exc:
        logger.exception("Scrape job %s crashed: %s", job_id, exc)
        try:
            async with AsyncSessionLocal() as session:
                job = await session.get(ScrapeJob, uuid.UUID(job_id))
                if job:
                    job.status = "failed"
                    job.error = str(exc)
                    await session.commit()
        except Exception:
            pass


@router.get("/scrape", response_model=list[ScrapeJobResponse])
async def list_scrape_jobs(_: CurrentUser) -> list[ScrapeJobResponse]:
    """List all scrape jobs (newest first)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ScrapeJob).order_by(ScrapeJob.created_at.desc()).limit(50)
        )
        jobs = result.scalars().all()
    return [ScrapeJobResponse.from_orm(j) for j in jobs]


@router.get("/scrape/{job_id}", response_model=ScrapeJobResponse)
async def get_scrape_job(job_id: str, _: CurrentUser) -> ScrapeJobResponse:
    """Get status of a single scrape job."""
    async with AsyncSessionLocal() as session:
        job = await session.get(ScrapeJob, uuid.UUID(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return ScrapeJobResponse.from_orm(job)


@router.delete("/scrape/{job_id}", status_code=204)
async def delete_scrape_job(job_id: str, _: AdminUser) -> None:
    """Delete a scrape job record. Cannot delete running jobs. Admin only."""
    async with AsyncSessionLocal() as session:
        job = await session.get(ScrapeJob, uuid.UUID(job_id))
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status in ("pending", "running"):
            raise HTTPException(status_code=409, detail="Cannot delete a job that is still running")
        await session.delete(job)
        await session.commit()


@router.get("/sources", response_model=list[SourceResponse])
async def list_sources(_: CurrentUser) -> list[SourceResponse]:
    """List all ingested knowledge sources."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(KnowledgeDocument).order_by(KnowledgeDocument.ingested_at.desc())
        )
        docs = result.scalars().all()
    return [SourceResponse.from_orm(d) for d in docs]


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(source_id: str, _: AdminUser) -> None:
    """Delete a knowledge source and all its chunks from ChromaDB. Admin only."""
    async with AsyncSessionLocal() as session:
        doc = await session.get(KnowledgeDocument, uuid.UUID(source_id))
        if not doc:
            raise HTTPException(status_code=404, detail="Source not found")
        source_url = doc.source
        await session.delete(doc)
        await session.commit()

    await delete_by_source(source_url)
