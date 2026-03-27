"""Knowledge base router — manage scrape jobs and stored knowledge sources."""

import logging
import os
import re
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.dependencies import CurrentUser, ManageKnowledgeUser
from app.models.knowledge import KnowledgeDocument
from app.models.knowledge_base import KnowledgeBase
from app.models.scrape_job import ScrapeJob
from app.models.scrape_job_log import ScrapeJobLog
from app.services.llm import embed_texts
from app.services.scraper import run_scrape_job
from app.services.vector_store import delete_by_source, get_source_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ── Request / Response schemas ────────────────────────────────────────────────


class ScrapeRequest(BaseModel):
    domain: str
    max_pages: int | None = 100  # None = unlimited
    max_size_mb: int | None = None  # e.g. 500 to stop after 500 MB of content
    topic_filter: str | None = None  # e.g. "patch management" or "MDM enrollment"
    knowledge_base_id: str | None = None


class ScrapeJobResponse(BaseModel):
    id: str
    domain: str
    max_pages: int | None
    max_size_mb: int | None
    topic_filter: str | None
    knowledge_base_id: str | None
    knowledge_base_name: str | None
    knowledge_base_dimension_tag: str | None
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
    continued_from_job_id: str | None
    last_url: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None

    @classmethod
    def from_orm(
        cls,
        job: ScrapeJob,
        knowledge_base: KnowledgeBase | None = None,
    ) -> "ScrapeJobResponse":
        return cls(
            id=str(job.id),
            domain=job.domain,
            max_pages=job.max_pages,
            max_size_mb=job.max_size_mb,
            topic_filter=job.topic_filter,
            knowledge_base_id=(str(job.knowledge_base_id) if job.knowledge_base_id else None),
            knowledge_base_name=(knowledge_base.name if knowledge_base else None),
            knowledge_base_dimension_tag=(knowledge_base.dimension_tag if knowledge_base else None),
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
            continued_from_job_id=str(job.continued_from_job_id) if job.continued_from_job_id else None,
            last_url=job.last_url,
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
    knowledge_base_id: str | None
    knowledge_base_name: str | None
    knowledge_base_dimension_tag: str | None
    ingested_at: str

    @classmethod
    def from_orm(
        cls,
        doc: KnowledgeDocument,
        knowledge_base: KnowledgeBase | None = None,
    ) -> "SourceResponse":
        return cls(
            id=str(doc.id),
            title=doc.title,
            source=doc.source,
            doc_type=doc.doc_type,
            chunk_count=doc.chunk_count,
            size_bytes=doc.size_bytes,
            knowledge_base_id=(str(doc.knowledge_base_id) if doc.knowledge_base_id else None),
            knowledge_base_name=(knowledge_base.name if knowledge_base else None),
            knowledge_base_dimension_tag=(knowledge_base.dimension_tag if knowledge_base else None),
            ingested_at=doc.ingested_at.isoformat(),
        )


class SourcePreviewResponse(BaseModel):
    source_id: str
    title: str
    source: str
    doc_type: str
    chunk_count: int
    size_bytes: int
    knowledge_base_name: str | None
    preview_text: str


class KnowledgeBaseCreateRequest(BaseModel):
    name: str
    description: str | None = None
    collection_name: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    dimension_tag: str | None = None
    is_default: bool = False


class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    description: str | None
    collection_name: str
    embedding_provider: str | None
    embedding_model: str | None
    embedding_dimension: int | None
    dimension_tag: str | None
    is_default: bool
    source_count: int = 0
    total_size_bytes: int = 0
    created_at: str
    updated_at: str

    @classmethod
    def from_orm(cls, kb: KnowledgeBase) -> "KnowledgeBaseResponse":
        return cls(
            id=str(kb.id),
            name=kb.name,
            description=kb.description,
            collection_name=kb.collection_name,
            embedding_provider=kb.embedding_provider,
            embedding_model=kb.embedding_model,
            embedding_dimension=kb.embedding_dimension,
            dimension_tag=kb.dimension_tag,
            is_default=kb.is_default,
            source_count=0,
            total_size_bytes=0,
            created_at=kb.created_at.isoformat(),
            updated_at=kb.updated_at.isoformat(),
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


def _slugify_collection(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    slug = slug[:90] if slug else "knowledge_base"
    return f"kb_{slug}"


async def _get_default_knowledge_base(session) -> KnowledgeBase:
    kb = (
        await session.execute(
            select(KnowledgeBase)
            .where(KnowledgeBase.is_default.is_(True))
            .order_by(KnowledgeBase.created_at.asc())
        )
    ).scalar_one_or_none()
    if kb:
        return kb

    first = (
        await session.execute(select(KnowledgeBase).order_by(KnowledgeBase.created_at.asc()))
    ).scalars().first()
    if first:
        first.is_default = True
        await session.commit()
        await session.refresh(first)
        return first

    settings = get_settings()
    kb = KnowledgeBase(
        name="Default Knowledge Base",
        description="Auto-created default knowledge base",
        collection_name="jamf_knowledge",
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model_name_effective,
        dimension_tag="legacy",
        is_default=True,
    )
    session.add(kb)
    await session.commit()
    await session.refresh(kb)
    return kb


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/bases", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(_: CurrentUser) -> list[KnowledgeBaseResponse]:
    """List configured knowledge bases."""
    async with AsyncSessionLocal() as session:
        default_kb = await _get_default_knowledge_base(session)
        result = await session.execute(
            select(KnowledgeBase).order_by(KnowledgeBase.is_default.desc(), KnowledgeBase.name.asc())
        )
        bases = result.scalars().all()
        if not bases:
            bases = [default_kb]

        doc_stats_result = await session.execute(
            select(
                KnowledgeDocument.knowledge_base_id,
                func.count(KnowledgeDocument.id),
                func.coalesce(func.sum(KnowledgeDocument.size_bytes), 0),
            )
            .group_by(KnowledgeDocument.knowledge_base_id)
        )
        doc_stats = {
            kb_id: {"source_count": int(count), "total_size_bytes": int(total_size)}
            for kb_id, count, total_size in doc_stats_result.all()
        }

    out: list[KnowledgeBaseResponse] = []
    for kb in bases:
        payload = KnowledgeBaseResponse.from_orm(kb)
        stats = doc_stats.get(kb.id, {"source_count": 0, "total_size_bytes": 0})
        payload.source_count = stats["source_count"]
        payload.total_size_bytes = stats["total_size_bytes"]
        out.append(payload)
    return out


@router.post("/bases", response_model=KnowledgeBaseResponse, status_code=201)
async def create_knowledge_base(
    body: KnowledgeBaseCreateRequest,
    _: ManageKnowledgeUser,
) -> KnowledgeBaseResponse:
    """Create a knowledge base with independent vector collection and embedding metadata."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    settings = get_settings()
    embedding_provider = body.embedding_provider or settings.embedding_provider
    embedding_model = body.embedding_model or settings.embedding_model_name_effective

    collection_name = (body.collection_name or _slugify_collection(name)).strip()
    if len(collection_name) < 3:
        raise HTTPException(status_code=400, detail="collection_name is too short")

    embedding_dimension = body.embedding_dimension
    if embedding_dimension is None:
        try:
            probe = await embed_texts(["dimension probe"])
            if probe and probe[0]:
                embedding_dimension = len(probe[0])
        except Exception as exc:
            logger.warning("Could not auto-detect embedding dimension for knowledge base create: %s", exc)

    async with AsyncSessionLocal() as session:
        name_exists = (
            await session.execute(select(KnowledgeBase).where(KnowledgeBase.name == name))
        ).scalar_one_or_none()
        if name_exists:
            raise HTTPException(status_code=409, detail="Knowledge base name already exists")

        collection_exists = (
            await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.collection_name == collection_name)
            )
        ).scalar_one_or_none()
        if collection_exists:
            raise HTTPException(status_code=409, detail="collection_name already exists")

        if body.is_default:
            await session.execute(select(KnowledgeBase))
            existing_default = (
                await session.execute(
                    select(KnowledgeBase).where(KnowledgeBase.is_default.is_(True))
                )
            ).scalars().all()
            for kb in existing_default:
                kb.is_default = False

        current_count = (await session.execute(select(KnowledgeBase))).scalars().all()
        should_set_default = body.is_default or len(current_count) == 0
        kb = KnowledgeBase(
            name=name,
            description=body.description,
            collection_name=collection_name,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
            dimension_tag=body.dimension_tag,
            is_default=should_set_default,
        )
        session.add(kb)
        await session.commit()
        await session.refresh(kb)

    return KnowledgeBaseResponse.from_orm(kb)


@router.delete("/bases/{knowledge_base_id}", status_code=204)
async def delete_knowledge_base(knowledge_base_id: str, _: ManageKnowledgeUser) -> None:
    """Delete a full knowledge base and all associated sources/chunks/jobs. Admin only."""
    try:
        kb_id = uuid.UUID(knowledge_base_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid knowledge_base_id") from exc

    async with AsyncSessionLocal() as session:
        kb = await session.get(KnowledgeBase, kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        running_jobs = (
            await session.execute(
                select(ScrapeJob).where(
                    ScrapeJob.knowledge_base_id == kb_id,
                    ScrapeJob.status.in_(["pending", "running"]),
                )
            )
        ).scalars().all()
        if running_jobs:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete knowledge base while scrape jobs are running",
            )

        all_bases = (await session.execute(select(KnowledgeBase).order_by(KnowledgeBase.created_at.asc()))).scalars().all()
        if len(all_bases) <= 1:
            raise HTTPException(status_code=409, detail="Cannot delete the last remaining knowledge base")

        docs = (
            await session.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.knowledge_base_id == kb_id)
            )
        ).scalars().all()

        jobs = (
            await session.execute(
                select(ScrapeJob).where(ScrapeJob.knowledge_base_id == kb_id)
            )
        ).scalars().all()

        if kb.is_default:
            replacement = next((base for base in all_bases if base.id != kb.id), None)
            if replacement:
                replacement.is_default = True

        for doc in docs:
            await session.delete(doc)

        for job in jobs:
            await session.execute(delete(ScrapeJobLog).where(ScrapeJobLog.job_id == job.id))
            await session.delete(job)

        await session.delete(kb)
        await session.commit()

    # Delete vector chunks after relational records are removed.
    for doc in docs:
        await delete_by_source(doc.source, collection_name=doc.collection_name or "jamf_knowledge")


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
        if body.knowledge_base_id:
            try:
                kb_id = uuid.UUID(body.knowledge_base_id)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid knowledge_base_id") from exc
            knowledge_base = await session.get(KnowledgeBase, kb_id)
            if not knowledge_base:
                raise HTTPException(status_code=404, detail="Knowledge base not found")
        else:
            knowledge_base = await _get_default_knowledge_base(session)

        job = ScrapeJob(
            domain=domain,
            max_pages=body.max_pages,  # None = unlimited
            max_size_mb=body.max_size_mb,
            topic_filter=body.topic_filter or None,
            knowledge_base_id=knowledge_base.id,
            status="pending",
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = str(job.id)

    background_tasks.add_task(_run_job_safe, job_id)
    return ScrapeJobResponse.from_orm(job, knowledge_base=knowledge_base)


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


def _is_interrupted_job(job: ScrapeJob) -> bool:
    return job.status == "failed" and bool(job.error and job.error.startswith("Interrupted:"))


@router.get("/scrape", response_model=list[ScrapeJobResponse])
async def list_scrape_jobs(_: CurrentUser) -> list[ScrapeJobResponse]:
    """List all scrape jobs (newest first)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ScrapeJob).order_by(ScrapeJob.created_at.desc()).limit(50)
        )
        jobs = result.scalars().all()
        kb_result = await session.execute(select(KnowledgeBase))
        kb_map = {kb.id: kb for kb in kb_result.scalars().all()}
    return [ScrapeJobResponse.from_orm(j, knowledge_base=kb_map.get(j.knowledge_base_id)) for j in jobs]


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
        kb = await session.get(KnowledgeBase, job.knowledge_base_id) if job and job.knowledge_base_id else None
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return ScrapeJobResponse.from_orm(job, knowledge_base=kb)


@router.post("/scrape/{job_id}/continue", response_model=ScrapeJobResponse, status_code=202)
async def continue_scrape_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    _: ManageKnowledgeUser,
) -> ScrapeJobResponse:
    """Restart an interrupted scrape job with the same settings."""
    async with AsyncSessionLocal() as session:
        job = await session.get(ScrapeJob, uuid.UUID(job_id))
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if not _is_interrupted_job(job):
            raise HTTPException(status_code=409, detail="Only interrupted jobs can be continued")

        continued_job = ScrapeJob(
            domain=job.domain,
            max_pages=job.max_pages,
            max_size_mb=job.max_size_mb,
            topic_filter=job.topic_filter,
            knowledge_base_id=job.knowledge_base_id,
            status="pending",
            cpu_cap_mode=job.cpu_cap_mode,
            cpu_cap_percent=job.cpu_cap_percent,
            continued_from_job_id=job.id,
        )
        session.add(continued_job)
        await session.commit()
        await session.refresh(continued_job)

        session.add(
            ScrapeJobLog(
                job_id=continued_job.id,
                level="info",
                message=(
                    f"Continuation created from interrupted job {job.id}"
                    + (f" at last URL {job.last_url}" if job.last_url else "")
                ),
            )
        )
        await session.commit()

    background_tasks.add_task(_run_job_safe, str(continued_job.id))
    async with AsyncSessionLocal() as session:
        kb = (
            await session.get(KnowledgeBase, continued_job.knowledge_base_id)
            if continued_job.knowledge_base_id
            else None
        )
    return ScrapeJobResponse.from_orm(continued_job, knowledge_base=kb)


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
        kb = await session.get(KnowledgeBase, job.knowledge_base_id) if job.knowledge_base_id else None
        return ScrapeJobResponse.from_orm(job, knowledge_base=kb)


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
async def list_sources(_: CurrentUser, knowledge_base_id: str | None = None) -> list[SourceResponse]:
    """List all ingested knowledge sources."""
    async with AsyncSessionLocal() as session:
        query = select(KnowledgeDocument)
        if knowledge_base_id:
            try:
                kb_id = uuid.UUID(knowledge_base_id)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid knowledge_base_id") from exc
            query = query.where(KnowledgeDocument.knowledge_base_id == kb_id)
        result = await session.execute(query.order_by(KnowledgeDocument.ingested_at.desc()))
        docs = result.scalars().all()
        kb_result = await session.execute(select(KnowledgeBase))
        kb_map = {kb.id: kb for kb in kb_result.scalars().all()}
    return [SourceResponse.from_orm(d, knowledge_base=kb_map.get(d.knowledge_base_id)) for d in docs]


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(source_id: str, _: ManageKnowledgeUser) -> None:
    """Delete a knowledge source and all its chunks from ChromaDB. Admin only."""
    async with AsyncSessionLocal() as session:
        doc = await session.get(KnowledgeDocument, uuid.UUID(source_id))
        if not doc:
            raise HTTPException(status_code=404, detail="Source not found")
        source_url = doc.source
        collection_name = doc.collection_name or "jamf_knowledge"
        await session.delete(doc)
        await session.commit()

    await delete_by_source(source_url, collection_name=collection_name)


@router.get("/sources/{source_id}/preview", response_model=SourcePreviewResponse)
async def get_source_preview(source_id: str, _: CurrentUser) -> SourcePreviewResponse:
    """Return a readable preview reconstructed from stored chunks for one source."""
    async with AsyncSessionLocal() as session:
        doc = await session.get(KnowledgeDocument, uuid.UUID(source_id))
        if not doc:
            raise HTTPException(status_code=404, detail="Source not found")
        kb = await session.get(KnowledgeBase, doc.knowledge_base_id) if doc.knowledge_base_id else None

    chunks = await get_source_chunks(
        doc.source,
        collection_name=doc.collection_name or "jamf_knowledge",
        limit=12,
    )
    preview_text = "\n\n".join(chunks).strip()
    if not preview_text:
        preview_text = "No readable preview available for this source yet."

    return SourcePreviewResponse(
        source_id=str(doc.id),
        title=doc.title,
        source=doc.source,
        doc_type=doc.doc_type,
        chunk_count=doc.chunk_count,
        size_bytes=doc.size_bytes,
        knowledge_base_name=(kb.name if kb else None),
        preview_text=preview_text,
    )
