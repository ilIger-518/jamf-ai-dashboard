"""Knowledge base router — manage scrape jobs and stored knowledge sources."""

import logging
import os
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.dependencies import CurrentUser, ManageKnowledgeUser
from app.models.knowledge import KnowledgeDocument
from app.models.scrape_job import ScrapeJob
from app.models.scrape_job_log import ScrapeJobLog
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
    pause_requested: bool
    cancel_requested: bool
    cpu_cap_mode: str
    cpu_cap_percent: int
    seed_mode: str
    seed_urls: int
    sitemap_timed_out: bool
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
            pause_requested=job.pause_requested,
            cancel_requested=job.cancel_requested,
            cpu_cap_mode=job.cpu_cap_mode,
            cpu_cap_percent=job.cpu_cap_percent,
            seed_mode=job.seed_mode,
            seed_urls=job.seed_urls,
            sitemap_timed_out=job.sitemap_timed_out,
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


class ScrapeControlRequest(BaseModel):
    action: str  # pause | resume | cancel
    cpu_cap_mode: str | None = None  # total | core
    cpu_cap_percent: int | None = None


class ScrapeJobLogResponse(BaseModel):
    id: str
    job_id: str
    level: str
    message: str
    created_at: str

    @classmethod
    def from_orm(cls, log: ScrapeJobLog) -> "ScrapeJobLogResponse":
        return cls(
            id=str(log.id),
            job_id=str(log.job_id),
            level=log.level,
            message=log.message,
            created_at=log.created_at.isoformat(),
        )


class ScrapeRuntimeResponse(BaseModel):
    job_id: str
    status: str
    cpu_cap_mode: str
    cpu_cap_percent: int
    cpu_cores: int
    allowed_cores: float
    embedding_threads: int
    pause_requested: bool
    cancel_requested: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/scrape", response_model=ScrapeJobResponse, status_code=202)
async def start_scrape(
    body: ScrapeRequest,
    background_tasks: BackgroundTasks,
    _: ManageKnowledgeUser,
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
                session.add(
                    ScrapeJobLog(
                        job_id=uuid.UUID(job_id),
                        level="error",
                        message=f"Job crashed: {exc}",
                    )
                )
                await session.commit()

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


@router.get("/scrape/system")
async def get_scrape_system_info(_: CurrentUser) -> dict:
    cores = max(1, (os.cpu_count() or 1))
    return {
        "cpu_cores": cores,
        "max_total_percent": 100,
        "max_core_percent": cores * 100,
    }


@router.get("/scrape/{job_id}", response_model=ScrapeJobResponse)
async def get_scrape_job(job_id: str, _: CurrentUser) -> ScrapeJobResponse:
    """Get status of a single scrape job."""
    async with AsyncSessionLocal() as session:
        job = await session.get(ScrapeJob, uuid.UUID(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return ScrapeJobResponse.from_orm(job)


@router.get("/scrape/{job_id}/logs", response_model=list[ScrapeJobLogResponse])
async def get_scrape_job_logs(
    job_id: str,
    _: CurrentUser,
    after_id: str | None = None,
    limit: int = 1000,
) -> list[ScrapeJobLogResponse]:
    """Return newest log lines for a scrape job; optionally only entries after a given id."""
    safe_limit = max(1, min(limit, 1000))

    async with AsyncSessionLocal() as session:
        job = await session.get(ScrapeJob, uuid.UUID(job_id))
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        query = select(ScrapeJobLog).where(ScrapeJobLog.job_id == uuid.UUID(job_id))

        if after_id:
            after_log = await session.get(ScrapeJobLog, uuid.UUID(after_id))
            if after_log and str(after_log.job_id) == job_id:
                query = query.where(ScrapeJobLog.created_at > after_log.created_at)

        result = await session.execute(
            query.order_by(ScrapeJobLog.created_at.asc()).limit(safe_limit)
        )
        logs = result.scalars().all()

    return [ScrapeJobLogResponse.from_orm(log) for log in logs]


@router.get("/scrape/{job_id}/runtime", response_model=ScrapeRuntimeResponse)
async def get_scrape_job_runtime(job_id: str, _: CurrentUser) -> ScrapeRuntimeResponse:
    """Expose computed runtime cap details for transparent throttling diagnostics."""
    async with AsyncSessionLocal() as session:
        job = await session.get(ScrapeJob, uuid.UUID(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    cores = max(1, (os.cpu_count() or 1))
    if job.cpu_cap_mode == "core":
        allowed_cores = max(0.01, min(job.cpu_cap_percent / 100.0, float(cores)))
        embedding_threads = max(1, min(cores, int((job.cpu_cap_percent + 99) // 100)))
    else:
        ratio = max(0.01, min(job.cpu_cap_percent, 100)) / 100.0
        allowed_cores = max(0.01, ratio * float(cores))
        embedding_threads = max(1, min(cores, int((cores * job.cpu_cap_percent + 99) // 100)))

    return ScrapeRuntimeResponse(
        job_id=str(job.id),
        status=job.status,
        cpu_cap_mode=job.cpu_cap_mode,
        cpu_cap_percent=job.cpu_cap_percent,
        cpu_cores=cores,
        allowed_cores=allowed_cores,
        embedding_threads=embedding_threads,
        pause_requested=job.pause_requested,
        cancel_requested=job.cancel_requested,
    )


@router.patch("/scrape/{job_id}", response_model=ScrapeJobResponse)
async def control_scrape_job(job_id: str, body: ScrapeControlRequest, _: ManageKnowledgeUser) -> ScrapeJobResponse:
    """Control a scrape job: pause/resume/cancel and update CPU cap settings."""
    if body.action not in {"pause", "resume", "cancel"}:
        raise HTTPException(status_code=400, detail="Invalid action")

    async with AsyncSessionLocal() as session:
        job = await session.get(ScrapeJob, uuid.UUID(job_id))
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.status not in {"pending", "running"} and body.action in {"pause", "resume", "cancel"}:
            raise HTTPException(status_code=409, detail="Job is no longer running")

        if body.cpu_cap_mode is not None:
            if body.cpu_cap_mode not in {"total", "core"}:
                raise HTTPException(status_code=400, detail="cpu_cap_mode must be 'total' or 'core'")
            job.cpu_cap_mode = body.cpu_cap_mode

        if body.cpu_cap_percent is not None:
            max_cap = 100 if job.cpu_cap_mode == "total" else max(1, (os.cpu_count() or 1)) * 100
            if body.cpu_cap_percent < 1 or body.cpu_cap_percent > max_cap:
                raise HTTPException(
                    status_code=400,
                    detail=f"cpu_cap_percent must be between 1 and {max_cap} for mode {job.cpu_cap_mode}",
                )
            job.cpu_cap_percent = body.cpu_cap_percent

        if body.action == "pause":
            job.pause_requested = True
        elif body.action == "resume":
            job.pause_requested = False
        elif body.action == "cancel":
            job.cancel_requested = True
            job.pause_requested = False

        await session.commit()
        await session.refresh(job)
        return ScrapeJobResponse.from_orm(job)


@router.delete("/scrape/{job_id}", status_code=204)
async def delete_scrape_job(job_id: str, _: ManageKnowledgeUser) -> None:
    """Delete a scrape job record. Cannot delete running jobs. Admin only."""
    async with AsyncSessionLocal() as session:
        job = await session.get(ScrapeJob, uuid.UUID(job_id))
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status in ("pending", "running"):
            raise HTTPException(status_code=409, detail="Cannot delete a job that is still running")
        await session.execute(delete(ScrapeJobLog).where(ScrapeJobLog.job_id == job.id))
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
async def delete_source(source_id: str, _: ManageKnowledgeUser) -> None:
    """Delete a knowledge source and all its chunks from ChromaDB. Admin only."""
    async with AsyncSessionLocal() as session:
        doc = await session.get(KnowledgeDocument, uuid.UUID(source_id))
        if not doc:
            raise HTTPException(status_code=404, detail="Source not found")
        source_url = doc.source
        await session.delete(doc)
        await session.commit()

    await delete_by_source(source_url)
