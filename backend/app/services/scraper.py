"""
Async web scraper service.

Features:
- BFS crawl of an entire domain up to max_pages
- Sitemap-seeded crawl: parses sitemap.xml (including sitemap index files) to
  build the initial queue, bypassing SPA shells that contain no links
- Zoomin Software API support: for documentation sites built on Zoomin
  (e.g. learn.jamf.com) fetches rich JSON content directly from the backend
  API instead of scraping the SPA HTML shell.  The API host is detected from
  the embedded page config when present; for sites that load config
  asynchronously via JavaScript (such as learn.jamf.com) a static fallback
  mapping (_ZOOMIN_KNOWN_API_HOSTS) is used.  SPA shell pages that cannot be
  resolved to real article content are skipped rather than stored.
- Login/redirect detection: skips pages that redirect to a different domain
- Optional topic_filter: uses the LLM to decide if a page is relevant before ingesting
- Stores progress in a ScrapeJob row (status, pages_scraped, pages_found, error)
"""

import asyncio
import hashlib
import logging
import os
import re
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeDocument
from app.models.knowledge_base import KnowledgeBase
from app.models.scrape_job import ScrapeJob
from app.models.scrape_job_log import ScrapeJobLog
from app.services.llm import complete_chat
from app.services.vector_store import ingest_document

logger = logging.getLogger(__name__)

_MAX_SUB_SITEMAPS = 40
_MAX_SEED_URLS = 3000
_MAX_QUEUE_URLS = 20000
_MAX_EMBED_TEXT_CHARS = 250_000
_SITEMAP_SEED_TIMEOUT_SECONDS = 90
_SUB_SITEMAP_CONCURRENCY = 8
_SCRAPE_FETCH_CONCURRENCY = max(1, min(8, int(os.environ.get("SCRAPE_FETCH_CONCURRENCY", "4"))))

# Matches Zoomin Software documentation page URLs:
# /[locale]/bundle/{bundleId}/page/{topicFile}.html
_ZOOMIN_PAGE_RE = re.compile(r"/bundle/([^/]+)/page/([^?#]+\.html)$", re.IGNORECASE)

# Known Zoomin SPA domain → backend API hostname mapping.
# Used as fallback when the API host cannot be detected from the page HTML
# (e.g. when the app config is loaded asynchronously via JavaScript).
_ZOOMIN_KNOWN_API_HOSTS: dict[str, str] = {
    "learn.jamf.com": "learn-be.jamf.com",
}

# Login/auth URL paths to skip
_LOGIN_PATH_RE = re.compile(r"/(login|signin|sign-in|auth|register|logout|sso)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _same_domain(base: str, url: str) -> bool:
    return urlparse(url).netloc == urlparse(base).netloc


def _normalize(url: str) -> str:
    """Canonicalize URL for de-duplication and strip tracking query params."""
    p = urlparse(url)
    query_pairs = parse_qsl(p.query, keep_blank_values=True)
    cleaned_query = urlencode(
        sorted(
            [
                (k, v)
                for (k, v) in query_pairs
                if not k.lower().startswith("utm_")
                and k.lower() not in {"fbclid", "gclid", "msclkid", "mc_cid", "mc_eid"}
            ]
        )
    )
    return p._replace(fragment="", query=cleaned_query).geturl().rstrip("/")


def _extract_text(html: str) -> str:
    """Parse HTML and return clean plain text, preferring <main>/<article> content."""
    soup = BeautifulSoup(html, "lxml")
    # Prefer semantic content regions to avoid nav/footer noise
    content = soup.find("main") or soup.find("article") or soup
    for tag in content(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    return " ".join(content.get_text(separator=" ").split())


def _extract_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href_raw = a.get("href")
        if not isinstance(href_raw, str):
            continue
        href = href_raw
        if href.startswith(("mailto:", "javascript:", "#")):
            continue
        full = urljoin(base_url, href)
        full = _normalize(full)
        if full.startswith("http"):
            links.append(full)
    return links


def _page_title(html: str, fallback_url: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    t = soup.find("title")
    return (t.get_text().strip() if t else fallback_url)[:512]


def _cpu_cap_to_allowed_cores(cpu_cap_mode: str, cpu_cap_percent: int) -> float:
    """
    Convert configured cap to allowed CPU core-seconds per wall second.

    This cap is interpreted as host-wide CPU budget for this job pipeline.
    """
    cores = max(1, (os.cpu_count() or 1))
    if cpu_cap_mode == "core":
        # Linux-style: 100 == one full core, 200 == two cores, etc.
        return max(0.01, min(cpu_cap_percent / 100.0, float(cores)))

    # Total mode: 0-100% of total host CPU capacity.
    total_ratio = max(0.01, min(cpu_cap_percent, 100)) / 100.0
    return max(0.01, total_ratio * float(cores))


def _cpu_cap_to_ollama_threads(cpu_cap_mode: str, cpu_cap_percent: int) -> int:
    """Map cap setting to an integer Ollama thread budget."""
    cores = max(1, (os.cpu_count() or 1))
    if cpu_cap_mode == "core":
        return max(1, min(cores, int((cpu_cap_percent + 99) // 100)))
    return max(1, min(cores, int((cores * cpu_cap_percent + 99) // 100)))


async def _append_job_log(job_id: str, message: str, level: str = "info") -> None:
    """Persist a log line for a scrape job. Failures here should not stop scraping."""
    try:
        async with AsyncSessionLocal() as session:
            session.add(
                ScrapeJobLog(
                    job_id=uuid.UUID(job_id),
                    level=level,
                    message=message,
                )
            )
            await session.commit()
    except Exception as exc:
        logger.debug("Failed to append scrape job log for %s: %s", job_id, exc)


async def _fetch_candidate_page(
    http: httpx.AsyncClient,
    url: str,
    start_netloc: str,
) -> dict:
    """Fetch and pre-parse a page; returns {'status': 'ok'|'skip', ...} payload."""
    resp = await http.get(url)
    if resp.status_code != 200:
        return {"status": "skip", "reason": f"HTTP {resp.status_code}"}

    final_netloc = urlparse(str(resp.url)).netloc
    if final_netloc != start_netloc:
        return {"status": "skip", "reason": f"redirected to different domain: {final_netloc}"}

    final_path = urlparse(str(resp.url)).path
    if _LOGIN_PATH_RE.search(final_path):
        return {"status": "skip", "reason": f"auth/login page: {resp.url}"}

    ct = resp.headers.get("content-type", "")
    if "text/html" not in ct:
        return {"status": "skip", "reason": f"non-HTML content ({ct or 'unknown content-type'})"}

    html = resp.text
    text = _extract_text(html)
    zoomin_title = ""
    topic_html_for_links: str | None = None

    if len(text) < 300:
        zoomin = await _try_zoomin_content(http, url, html)
        if zoomin:
            topic_html, zoomin_title = zoomin
            text = _extract_text(topic_html)
            # Use the API-rendered topic HTML for link discovery so that
            # inter-article links are followed during the crawl.
            topic_html_for_links = topic_html
        elif urlparse(url).netloc in _ZOOMIN_KNOWN_API_HOSTS:
            # This is a SPA shell page on a known Zoomin domain (e.g. the
            # homepage or a navigation page) that contains no article content.
            # Skip it to avoid storing the generic loading-screen placeholder
            # text in the knowledge base.
            return {
                "status": "skip",
                "reason": "Zoomin SPA shell page without extractable content",
            }

    if len(text) < 100:
        return {"status": "skip", "reason": f"low-content page ({len(text)} chars)"}

    link_source_html = topic_html_for_links if topic_html_for_links is not None else html
    links = [link for link in _extract_links(link_source_html, url) if _same_domain(url, link)]

    return {
        "status": "ok",
        "html": html,
        "text": text,
        "zoomin_title": zoomin_title,
        "links": links,
    }


# ---------------------------------------------------------------------------
# Sitemap seeding
# ---------------------------------------------------------------------------


async def _fetch_sub_sitemap_urls(
    http: httpx.AsyncClient,
    start_url: str,
    sub_url: str,
    semaphore: asyncio.Semaphore,
) -> list[str]:
    async with semaphore:
        try:
            sub_resp = await http.get(sub_url, timeout=20)
            if sub_resp.status_code != 200:
                return []
            sub_soup = BeautifulSoup(sub_resp.text, "lxml-xml")
            urls: list[str] = []
            for loc in sub_soup.select("urlset > url > loc"):
                candidate = _normalize(loc.text.strip())
                if _same_domain(start_url, candidate):
                    urls.append(candidate)
                    if len(urls) >= _MAX_SEED_URLS:
                        break
            return urls
        except Exception as exc:
            logger.debug("Failed to fetch sub-sitemap %s: %s", sub_url, exc)
            return []


async def _seed_from_sitemap(http: httpx.AsyncClient, start_url: str) -> tuple[list[str], bool]:
    """
    Try to fetch /sitemap.xml and extract all same-domain URLs.
    Handles both sitemap index (sitemapindex) and regular sitemaps (urlset).
    Returns (urls, sitemap_timed_out).
    """
    parsed = urlparse(start_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    urls: list[str] = []
    timed_out = False
    try:
        resp = await http.get(f"{base}/sitemap.xml", timeout=20)
        if resp.status_code != 200:
            logger.debug("No sitemap.xml at %s (status %s)", base, resp.status_code)
            return urls, timed_out

        soup = BeautifulSoup(resp.text, "lxml-xml")

        # Sitemap index: <sitemapindex><sitemap><loc>…</loc></sitemap>…</sitemapindex>
        sub_locs = [loc.text.strip() for loc in soup.select("sitemapindex > sitemap > loc")]
        if sub_locs:
            semaphore = asyncio.Semaphore(_SUB_SITEMAP_CONCURRENCY)
            results = await asyncio.gather(
                *[
                    _fetch_sub_sitemap_urls(http, start_url, sub_url, semaphore)
                    for sub_url in sub_locs[:_MAX_SUB_SITEMAPS]
                ]
            )
            for batch in results:
                urls.extend(batch)
                if len(urls) >= _MAX_SEED_URLS:
                    urls = urls[:_MAX_SEED_URLS]
                    break
        else:
            # Direct urlset sitemap
            for loc in soup.select("urlset > url > loc"):
                candidate = _normalize(loc.text.strip())
                if _same_domain(start_url, candidate):
                    urls.append(candidate)
                    if len(urls) >= _MAX_SEED_URLS:
                        break

        logger.info("Sitemap seeding: found %d URLs for %s", len(urls), start_url)
    except Exception as exc:
        logger.info("Sitemap unavailable for %s: %s", start_url, exc)
    return urls, timed_out


# ---------------------------------------------------------------------------
# Zoomin Software documentation platform support
# ---------------------------------------------------------------------------


def _detect_zoomin_api_host(html: str) -> str | None:
    """
    Extract the Zoomin backend API hostname from the embedded app config block.
    Looks for: "api":{"host":"learn-be.jamf.com"}  (or similar)
    """
    m = re.search(r'"api"\s*:\s*\{[^}]*"host"\s*:\s*"([^"]+)"', html)
    return m.group(1) if m else None


async def _try_zoomin_content(
    http: httpx.AsyncClient, url: str, page_html: str
) -> tuple[str, str] | None:
    """
    If the URL matches a Zoomin documentation page pattern AND the page HTML
    contains a Zoomin config (or the domain is a known Zoomin host), fetch the
    article content via the backend JSON API.

    Returns (article_html, title) or None if not applicable / API unreachable.
    """
    path = urlparse(url).path
    m = _ZOOMIN_PAGE_RE.search(path)
    if not m:
        return None

    parsed = urlparse(url)
    # Prefer the API host embedded in the page config; fall back to the
    # static known-host mapping for sites (like learn.jamf.com) that load
    # their config asynchronously via JavaScript.
    api_host = _detect_zoomin_api_host(page_html) or _ZOOMIN_KNOWN_API_HOSTS.get(parsed.netloc)
    if not api_host:
        return None

    bundle, topic = m.group(1), m.group(2)
    api_url = f"https://{api_host}/api/bundle/{bundle}/page/{topic}"
    origin = f"{parsed.scheme}://{parsed.netloc}"

    try:
        api_resp = await http.get(
            api_url,
            timeout=20,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Origin": origin,
                "Referer": url,
            },
        )
        if api_resp.status_code != 200:
            logger.debug("Zoomin API %s returned %s", api_url, api_resp.status_code)
            return None
        data = api_resp.json()
        topic_html: str = data.get("topic_html") or ""
        title: str = data.get("title") or data.get("searchtitle") or ""
        if not topic_html or len(topic_html) < 100:
            return None
        return topic_html, title
    except Exception as exc:
        logger.debug("Zoomin API call failed for %s: %s", url, exc)
        return None


async def _llm_is_relevant(text_snippet: str, topic_filter: str) -> bool:
    """
    Ask the configured AI provider whether this page is relevant to topic_filter.
    Returns True if relevant, False to skip.
    """
    prompt = (
        f"You are a content classifier. Answer only YES or NO.\n"
        f"Topic filter: {topic_filter}\n"
        f"Page snippet (first 600 chars): {text_snippet[:600]}\n"
        f"Is this page relevant to the topic filter?"
    )
    try:
        answer = (
            (
                await complete_chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.0,
                    timeout=20.0,
                    use_case="scrape",
                )
            )
            .strip()
            .upper()
        )
        return answer.startswith("Y")
    except Exception as exc:
        logger.warning("Topic filter LLM call failed (%s), including page by default", exc)
        return True  # include on error


# ---------------------------------------------------------------------------
# Main scrape coroutine — runs in background
# ---------------------------------------------------------------------------


async def run_scrape_job(job_id: str) -> None:
    """
    Background coroutine.  Reads job config from DB, crawls, embeds, updates progress.
    """
    logger.info("Starting scrape job %s", job_id)
    await _append_job_log(job_id, "Job started")

    continued_from_job_id: uuid.UUID | None = None
    knowledge_base_id: uuid.UUID | None = None
    knowledge_collection_name = "jamf_knowledge"
    knowledge_base_name = "default"

    async with AsyncSessionLocal() as session:
        job = await session.get(ScrapeJob, uuid.UUID(job_id))
        if not job:
            logger.error("ScrapeJob %s not found", job_id)
            return

        start_url = _normalize(job.domain)
        max_pages = job.max_pages  # None = unlimited
        max_size_bytes = (job.max_size_mb * 1024 * 1024) if job.max_size_mb else None
        topic_filter = job.topic_filter or ""
        continued_from_job_id = job.continued_from_job_id
        knowledge_base_id = job.knowledge_base_id

        if knowledge_base_id:
            kb = await session.get(KnowledgeBase, knowledge_base_id)
        else:
            kb = (
                await session.execute(
                    select(KnowledgeBase)
                    .where(KnowledgeBase.is_default.is_(True))
                    .order_by(KnowledgeBase.created_at.asc())
                )
            ).scalar_one_or_none()
            if kb:
                job.knowledge_base_id = kb.id
                knowledge_base_id = kb.id

        if kb:
            knowledge_collection_name = kb.collection_name
            knowledge_base_name = kb.name

        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.last_url = None
        await session.commit()

    await _append_job_log(
        job_id,
        f"Knowledge base scope: {knowledge_base_name} ({knowledge_collection_name})",
    )

    visited: set[str] = set()
    queue: deque[str] = deque()
    queued: set[str] = set()
    pages_scraped = 0
    bytes_scraped = 0
    errors: list[str] = []
    limiter_log_every = 10

    def _enqueue(candidate_url: str) -> bool:
        if candidate_url in visited or candidate_url in queued:
            return False
        if len(queued) >= _MAX_QUEUE_URLS:
            return False
        queue.append(candidate_url)
        queued.add(candidate_url)
        return True

    # Respect robots.txt at a basic level — skip common non-content paths
    SKIP_PATTERNS = re.compile(
        r"\.(css|js|png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|pdf|zip|gz|xml|json)$",
        re.IGNORECASE,
    )

    async with httpx.AsyncClient(
        timeout=15.0,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; JamfAIDashboard/1.0; +knowledge-base-crawler)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        follow_redirects=True,
    ) as http:
        start_netloc = urlparse(start_url).netloc

        if continued_from_job_id:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(KnowledgeDocument.source).where(
                        KnowledgeDocument.doc_type == "url",
                        KnowledgeDocument.knowledge_base_id == knowledge_base_id,
                    )
                )
                resumed_urls = {
                    _normalize(source)
                    for source in result.scalars().all()
                    if source and urlparse(source).netloc == start_netloc
                }
                if resumed_urls:
                    visited.update(resumed_urls)
                    await _append_job_log(
                        job_id,
                        f"Continuation preloaded {len(resumed_urls)} previously ingested URLs for this domain",
                    )

        # ----------------------------------------------------------------
        # Seed the queue: try sitemap first, fall back to start URL
        # ----------------------------------------------------------------
        sitemap_timed_out = False
        try:
            sitemap_urls, _ = await asyncio.wait_for(
                _seed_from_sitemap(http, start_url),
                timeout=_SITEMAP_SEED_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning("Sitemap seeding timed out for %s; falling back to start URL", start_url)
            sitemap_urls = []
            sitemap_timed_out = True
            await _append_job_log(
                job_id, "Sitemap seeding timed out; falling back to start URL", "warning"
            )

        if sitemap_urls:
            # For multi-language sites prefer English pages where locale is visible
            en_urls = [u for u in sitemap_urls if "/en-US/" in u or "/en/" in u]
            seed = en_urls if en_urls else sitemap_urls
            for seed_url in seed:
                _enqueue(seed_url)
            logger.info("Queue seeded with %d URLs from sitemap", len(queue))
            seed_mode = "sitemap"
            await _append_job_log(job_id, f"Queue seeded from sitemap with {len(queue)} URLs")
        else:
            _enqueue(start_url)
            seed_mode = "start_url"
            await _append_job_log(job_id, "Queue seeded from start URL")

        await _append_job_log(job_id, f"Starting crawl loop with queue size {len(queue)}")

        # Persist early signal so UI doesn't look idle at 0/0 while crawling starts.
        async with AsyncSessionLocal() as session:
            job_row = await session.get(ScrapeJob, uuid.UUID(job_id))
            if job_row:
                job_row.pages_found = len(queue)
                job_row.seed_mode = seed_mode
                job_row.seed_urls = len(queue)
                job_row.sitemap_timed_out = sitemap_timed_out
                await session.commit()

        throttle_wall_last = time.perf_counter()
        throttle_cpu_last = time.process_time()

        while queue and (max_pages is None or pages_scraped < max_pages):
            cpu_cap_mode = "total"
            cpu_cap_percent = 100

            try:
                # Runtime controls: pause/cancel/cpu cap can be changed from UI while running.
                async with AsyncSessionLocal() as session:
                    ctrl = await session.get(ScrapeJob, uuid.UUID(job_id))
                    if ctrl and ctrl.cancel_requested:
                        ctrl.status = "failed"
                        ctrl.error = "Cancelled by user"
                        ctrl.finished_at = datetime.now(UTC)
                        ctrl.pages_scraped = pages_scraped
                        ctrl.pages_found = len(visited)
                        ctrl.bytes_scraped = bytes_scraped
                        await session.commit()
                        logger.info("Scrape job %s cancelled", job_id)
                        await _append_job_log(job_id, "Job cancelled by user", "warning")
                        return

                    while ctrl and ctrl.pause_requested:
                        await asyncio.sleep(1.0)
                        await session.refresh(ctrl)
                        if ctrl.cancel_requested:
                            ctrl.status = "failed"
                            ctrl.error = "Cancelled by user"
                            ctrl.finished_at = datetime.now(UTC)
                            ctrl.pages_scraped = pages_scraped
                            ctrl.pages_found = len(visited)
                            ctrl.bytes_scraped = bytes_scraped
                            await session.commit()
                            logger.info("Scrape job %s cancelled while paused", job_id)
                            await _append_job_log(
                                job_id, "Job cancelled by user while paused", "warning"
                            )
                            return

                    cpu_cap_mode = ctrl.cpu_cap_mode if ctrl else "total"
                    cpu_cap_percent = ctrl.cpu_cap_percent if ctrl else 100

                # Stop if size limit reached
                if max_size_bytes and bytes_scraped >= max_size_bytes:
                    logger.info("Size limit reached (%.1f MB), stopping.", bytes_scraped / 1048576)
                    await _append_job_log(
                        job_id,
                        f"Size limit reached at {(bytes_scraped / 1048576):.1f} MB; stopping",
                    )
                    break

                batch_urls: list[str] = []
                while queue and len(batch_urls) < _SCRAPE_FETCH_CONCURRENCY:
                    candidate_url = queue.popleft()
                    queued.discard(candidate_url)
                    if candidate_url in visited:
                        continue
                    if SKIP_PATTERNS.search(urlparse(candidate_url).path):
                        await _append_job_log(
                            job_id, f"Skipping non-content URL by extension: {candidate_url}"
                        )
                        continue
                    visited.add(candidate_url)
                    batch_urls.append(candidate_url)

                if not batch_urls:
                    continue

                await _append_job_log(
                    job_id,
                    f"Fetching batch of {len(batch_urls)} page(s) with concurrency cap {_SCRAPE_FETCH_CONCURRENCY}",
                )

                fetch_results = await asyncio.gather(
                    *[_fetch_candidate_page(http, u, start_netloc) for u in batch_urls],
                    return_exceptions=True,
                )

                for url, fetched in zip(batch_urls, fetch_results, strict=False):
                    async with AsyncSessionLocal() as session:
                        job_row = await session.get(ScrapeJob, uuid.UUID(job_id))
                        if job_row:
                            job_row.last_url = url
                            await session.commit()
                    await _append_job_log(job_id, f"Visiting: {url}")

                    if isinstance(fetched, Exception):
                        logger.warning("Failed to fetch %s: %s", url, fetched)
                        errors.append(f"{url}: {fetched}")
                        await _append_job_log(job_id, f"Failed to fetch {url}: {fetched}", "error")
                        continue

                    if not isinstance(fetched, dict):
                        logger.warning(
                            "Unexpected fetch result type for %s: %s", url, type(fetched)
                        )
                        errors.append(f"{url}: unexpected fetch result type")
                        await _append_job_log(
                            job_id,
                            f"Failed to fetch {url}: unexpected fetch result type",
                            "error",
                        )
                        continue

                    if fetched.get("status") != "ok":
                        await _append_job_log(
                            job_id,
                            f"Skipped {url} ({fetched.get('reason', 'unknown reason')})",
                            "warning",
                        )
                        continue

                    html = str(fetched["html"])
                    text = str(fetched["text"])
                    zoomin_title = str(fetched.get("zoomin_title") or "")
                    child_links = list(fetched.get("links") or [])

                    if len(text) > _MAX_EMBED_TEXT_CHARS:
                        await _append_job_log(
                            job_id,
                            f"Truncated very large page before embedding: {url} ({len(text)} chars)",
                            "warning",
                        )
                        text = text[:_MAX_EMBED_TEXT_CHARS]

                    doc_size = len(text.encode("utf-8", errors="replace"))
                    content_hash = hashlib.sha256(
                        text.encode("utf-8", errors="replace")
                    ).hexdigest()

                    existing: KnowledgeDocument | None = None
                    async with AsyncSessionLocal() as session:
                        existing = (
                            await session.execute(
                                select(KnowledgeDocument).where(
                                    KnowledgeDocument.source == url,
                                    KnowledgeDocument.knowledge_base_id == knowledge_base_id,
                                )
                            )
                        ).scalar_one_or_none()

                    # Topic filter check
                    if topic_filter:
                        relevant = await _llm_is_relevant(text, topic_filter)
                        if not relevant:
                            logger.debug("Skipping (off-topic): %s", url)
                            await _append_job_log(job_id, f"Skipped off-topic page: {url}")
                            for link in child_links:
                                _enqueue(link)
                            continue

                    title = zoomin_title or _page_title(html, url)
                    embedding_threads = _cpu_cap_to_ollama_threads(cpu_cap_mode, cpu_cap_percent)
                    if existing and existing.file_hash == content_hash:
                        chunk_count = existing.chunk_count
                        await _append_job_log(job_id, f"Skipped re-embedding unchanged page: {url}")
                    else:
                        await _append_job_log(
                            job_id,
                            (
                                f"Embedding with thread cap {embedding_threads} "
                                f"(mode={cpu_cap_mode}, cap={cpu_cap_percent}%)"
                            ),
                        )
                        # Embed + store in ChromaDB
                        chunk_count, _ = await ingest_document(
                            source_url=url,
                            title=title,
                            text=text,
                            num_thread=embedding_threads,
                            collection_name=knowledge_collection_name,
                        )

                    bytes_scraped += len(html.encode("utf-8", errors="replace"))

                    # Record in Postgres
                    async with AsyncSessionLocal() as session:
                        existing = (
                            await session.execute(
                                select(KnowledgeDocument).where(
                                    KnowledgeDocument.source == url,
                                    KnowledgeDocument.knowledge_base_id == knowledge_base_id,
                                )
                            )
                        ).scalar_one_or_none()
                        if existing:
                            existing.chunk_count = chunk_count
                            existing.title = title
                            existing.size_bytes = doc_size
                            existing.file_hash = content_hash
                        else:
                            session.add(
                                KnowledgeDocument(
                                    title=title,
                                    source=url,
                                    doc_type="url",
                                    chunk_count=chunk_count,
                                    size_bytes=doc_size,
                                    file_hash=content_hash,
                                    collection_name=knowledge_collection_name,
                                    knowledge_base_id=knowledge_base_id,
                                )
                            )
                        await session.commit()

                    pages_scraped += 1
                    logger.info(
                        "Scraped page %d (%.1f MB): %s",
                        pages_scraped,
                        bytes_scraped / 1048576,
                        url,
                    )
                    await _append_job_log(
                        job_id,
                        f"Scraped page {pages_scraped}: {url}",
                    )

                    # Update progress in job row every 5 pages
                    if pages_scraped % 5 == 0:
                        async with AsyncSessionLocal() as session:
                            job_row = await session.get(ScrapeJob, uuid.UUID(job_id))
                            if job_row:
                                job_row.pages_scraped = pages_scraped
                                job_row.pages_found = len(visited) + len(queued)
                                job_row.bytes_scraped = bytes_scraped
                                job_row.last_url = url
                                await session.commit()

                    # Enqueue child links
                    added_links = 0
                    dropped_links = 0
                    for link in child_links:
                        if _enqueue(link):
                            added_links += 1
                        else:
                            dropped_links += 1

                    if added_links:
                        await _append_job_log(
                            job_id,
                            f"Discovered {added_links} new links from {url}; queue size now {len(queue)}",
                        )
                    if dropped_links and len(queued) >= _MAX_QUEUE_URLS:
                        await _append_job_log(
                            job_id,
                            f"Queue cap reached ({_MAX_QUEUE_URLS}); dropped {dropped_links} discovered links",
                            "warning",
                        )

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Scrape batch loop error: %s", exc)
                errors.append(f"batch: {exc}")
                await _append_job_log(job_id, f"Scrape batch loop error: {exc}", "error")
                continue
            finally:
                # Enforce CPU cap on every loop pass, including early-continue branches.
                allowed_cores = _cpu_cap_to_allowed_cores(cpu_cap_mode, cpu_cap_percent)
                wall_now = time.perf_counter()
                cpu_now = time.process_time()
                wall_elapsed = max(0.0, wall_now - throttle_wall_last)
                cpu_elapsed = max(0.0, cpu_now - throttle_cpu_last)

                if wall_elapsed > 0.0 and allowed_cores > 0.0:
                    required_wall = cpu_elapsed / allowed_cores
                    sleep_seconds = min(2.0, max(0.0, required_wall - wall_elapsed))
                    if sleep_seconds > 0:
                        await asyncio.sleep(sleep_seconds)

                    if pages_scraped > 0 and pages_scraped % limiter_log_every == 0:
                        await _append_job_log(
                            job_id,
                            (
                                f"Limiter: mode={cpu_cap_mode} cap={cpu_cap_percent}% "
                                f"allowed_cores={allowed_cores:.2f} cpu={cpu_elapsed:.3f}s "
                                f"wall={wall_elapsed:.3f}s sleep={sleep_seconds:.3f}s"
                            ),
                        )

                throttle_wall_last = time.perf_counter()
                throttle_cpu_last = time.process_time()

    # Finalise job
    async with AsyncSessionLocal() as session:
        job_row = await session.get(ScrapeJob, uuid.UUID(job_id))
        if job_row:
            job_row.status = "completed" if not errors else "completed_with_errors"
            job_row.pages_scraped = pages_scraped
            job_row.pages_found = len(visited) + len(queued)
            job_row.bytes_scraped = bytes_scraped
            job_row.last_url = None
            job_row.finished_at = datetime.now(UTC)
            if errors:
                job_row.error = f"{len(errors)} page(s) failed. First: {errors[0]}"
            await session.commit()

    await _append_job_log(
        job_id,
        f"Job finished with status {('completed' if not errors else 'completed_with_errors')}. "
        f"Pages scraped: {pages_scraped}",
        "info" if not errors else "warning",
    )
    logger.info("Scrape job %s finished: %d pages ingested", job_id, pages_scraped)
