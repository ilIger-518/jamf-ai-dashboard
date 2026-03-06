"""
Async web scraper service.

Features:
- BFS crawl of an entire domain up to max_pages
- Sitemap-seeded crawl: parses sitemap.xml (including sitemap index files) to
  build the initial queue, bypassing SPA shells that contain no links
- Zoomin Software API support: for documentation sites built on Zoomin
  (e.g. learn.jamf.com) fetches rich JSON content directly from the backend
  API instead of scraping the SPA HTML shell
- Login/redirect detection: skips pages that redirect to a different domain
- Optional topic_filter: uses the LLM to decide if a page is relevant before ingesting
- Stores progress in a ScrapeJob row (status, pages_scraped, pages_found, error)
"""

import asyncio
import logging
import re
import uuid
from collections import deque
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.knowledge import KnowledgeDocument
from app.models.scrape_job import ScrapeJob
from app.services.vector_store import ingest_document

logger = logging.getLogger(__name__)

# Matches Zoomin Software documentation page URLs:
# /[locale]/bundle/{bundleId}/page/{topicFile}.html
_ZOOMIN_PAGE_RE = re.compile(r"/bundle/([^/]+)/page/([^?#]+\.html)$", re.IGNORECASE)

# Login/auth URL paths to skip
_LOGIN_PATH_RE = re.compile(r"/(login|signin|sign-in|auth|register|logout|sso)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _same_domain(base: str, url: str) -> bool:
    return urlparse(url).netloc == urlparse(base).netloc


def _normalize(url: str) -> str:
    """Strip fragments and trailing slashes for de-duplication."""
    p = urlparse(url)
    return p._replace(fragment="").geturl().rstrip("/")


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
        href = a["href"]
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


# ---------------------------------------------------------------------------
# Sitemap seeding
# ---------------------------------------------------------------------------


async def _seed_from_sitemap(http: httpx.AsyncClient, start_url: str) -> list[str]:
    """
    Try to fetch /sitemap.xml and extract all same-domain URLs.
    Handles both sitemap index (sitemapindex) and regular sitemaps (urlset).
    Returns an empty list if no sitemap is found or parsing fails.
    """
    parsed = urlparse(start_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    urls: list[str] = []
    try:
        resp = await http.get(f"{base}/sitemap.xml", timeout=20)
        if resp.status_code != 200:
            logger.debug("No sitemap.xml at %s (status %s)", base, resp.status_code)
            return urls

        soup = BeautifulSoup(resp.text, "lxml-xml")

        # Sitemap index: <sitemapindex><sitemap><loc>…</loc></sitemap>…</sitemapindex>
        sub_locs = [loc.text.strip() for loc in soup.select("sitemapindex > sitemap > loc")]
        if sub_locs:
            for sub_url in sub_locs:
                try:
                    sub_resp = await http.get(sub_url, timeout=20)
                    if sub_resp.status_code != 200:
                        continue
                    sub_soup = BeautifulSoup(sub_resp.text, "lxml-xml")
                    for loc in sub_soup.select("urlset > url > loc"):
                        candidate = _normalize(loc.text.strip())
                        if _same_domain(start_url, candidate):
                            urls.append(candidate)
                except Exception as exc:
                    logger.debug("Failed to fetch sub-sitemap %s: %s", sub_url, exc)
        else:
            # Direct urlset sitemap
            for loc in soup.select("urlset > url > loc"):
                candidate = _normalize(loc.text.strip())
                if _same_domain(start_url, candidate):
                    urls.append(candidate)

        logger.info("Sitemap seeding: found %d URLs for %s", len(urls), start_url)
    except Exception as exc:
        logger.info("Sitemap unavailable for %s: %s", start_url, exc)
    return urls


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
    contains a Zoomin config, fetch the article content via the backend JSON API.

    Returns (article_html, title) or None if not applicable / API unreachable.
    """
    path = urlparse(url).path
    m = _ZOOMIN_PAGE_RE.search(path)
    if not m:
        return None

    api_host = _detect_zoomin_api_host(page_html)
    if not api_host:
        return None

    bundle, topic = m.group(1), m.group(2)
    api_url = f"https://{api_host}/api/bundle/{bundle}/page/{topic}"
    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

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
    Ask the local LLM whether this page is relevant to topic_filter.
    Returns True if relevant, False to skip.
    """
    from app.config import get_settings

    settings = get_settings()
    prompt = (
        f"You are a content classifier. Answer only YES or NO.\n"
        f"Topic filter: {topic_filter}\n"
        f"Page snippet (first 600 chars): {text_snippet[:600]}\n"
        f"Is this page relevant to the topic filter?"
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0.0},
                },
            )
            resp.raise_for_status()
            answer = resp.json()["message"]["content"].strip().upper()
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

    async with AsyncSessionLocal() as session:
        job = await session.get(ScrapeJob, uuid.UUID(job_id))
        if not job:
            logger.error("ScrapeJob %s not found", job_id)
            return

        start_url = _normalize(job.domain)
        max_pages = job.max_pages  # None = unlimited
        max_size_bytes = (job.max_size_mb * 1024 * 1024) if job.max_size_mb else None
        topic_filter = job.topic_filter or ""

        job.status = "running"
        job.started_at = datetime.now(UTC)
        await session.commit()

    visited: set[str] = set()
    queue: deque[str] = deque()
    pages_scraped = 0
    bytes_scraped = 0
    errors: list[str] = []

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
        # ----------------------------------------------------------------
        # Seed the queue: try sitemap first, fall back to start URL
        # ----------------------------------------------------------------
        sitemap_urls = await _seed_from_sitemap(http, start_url)
        if sitemap_urls:
            # For multi-language sites prefer English pages where locale is visible
            en_urls = [u for u in sitemap_urls if "/en-US/" in u or "/en/" in u]
            seed = en_urls if en_urls else sitemap_urls
            queue.extend(seed)
            logger.info("Queue seeded with %d URLs from sitemap", len(queue))
        else:
            queue.append(start_url)

        start_netloc = urlparse(start_url).netloc

        while queue and (max_pages is None or pages_scraped < max_pages):
            # Stop if size limit reached
            if max_size_bytes and bytes_scraped >= max_size_bytes:
                logger.info("Size limit reached (%.1f MB), stopping.", bytes_scraped / 1048576)
                break
            url = queue.popleft()
            if url in visited:
                continue
            if SKIP_PATTERNS.search(urlparse(url).path):
                continue
            visited.add(url)

            try:
                resp = await http.get(url)
                if resp.status_code != 200:
                    continue

                # Login/redirect detection: skip if redirected outside the original domain
                final_netloc = urlparse(str(resp.url)).netloc
                if final_netloc != start_netloc:
                    logger.debug("Skipping %s — redirected to %s (login?)", url, final_netloc)
                    continue

                # Skip login / auth pages by URL path
                final_path = urlparse(str(resp.url)).path
                if _LOGIN_PATH_RE.search(final_path):
                    logger.debug("Skipping login/auth page: %s", resp.url)
                    continue

                ct = resp.headers.get("content-type", "")
                if "text/html" not in ct:
                    continue

                html = resp.text
                text = _extract_text(html)

                # If text extraction yielded very little content, check whether
                # this is a Zoomin Software SPA and try the backend JSON API
                zoomin_title: str = ""
                if len(text) < 300:
                    zoomin = await _try_zoomin_content(http, url, html)
                    if zoomin:
                        topic_html, zoomin_title = zoomin
                        text = _extract_text(topic_html)
                        logger.debug("Used Zoomin API for %s (%d chars)", url, len(text))

                if len(text) < 100:
                    continue

                # Topic filter check
                if topic_filter:
                    relevant = await _llm_is_relevant(text, topic_filter)
                    if not relevant:
                        logger.debug("Skipping (off-topic): %s", url)
                        # Still enqueue child links so we don't miss nested pages
                        for link in _extract_links(html, url):
                            if _same_domain(start_url, link) and link not in visited:
                                queue.append(link)
                        continue

                title = zoomin_title or _page_title(html, url)

                # Embed + store in ChromaDB
                chunk_count, _ = await ingest_document(
                    source_url=url,
                    title=title,
                    text=text,
                )

                bytes_scraped += len(html.encode("utf-8", errors="replace"))

                # Record in Postgres
                async with AsyncSessionLocal() as session:
                    existing = (
                        await session.execute(
                            select(KnowledgeDocument).where(KnowledgeDocument.source == url)
                        )
                    ).scalar_one_or_none()
                    doc_size = len(text.encode("utf-8", errors="replace"))
                    if existing:
                        existing.chunk_count = chunk_count
                        existing.title = title
                        existing.size_bytes = doc_size
                    else:
                        session.add(
                            KnowledgeDocument(
                                title=title,
                                source=url,
                                doc_type="url",
                                chunk_count=chunk_count,
                                size_bytes=doc_size,
                                collection_name="jamf_knowledge",
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

                # Update progress in job row every 5 pages
                if pages_scraped % 5 == 0:
                    async with AsyncSessionLocal() as session:
                        job_row = await session.get(ScrapeJob, uuid.UUID(job_id))
                        if job_row:
                            job_row.pages_scraped = pages_scraped
                            job_row.pages_found = len(visited)
                            job_row.bytes_scraped = bytes_scraped
                            await session.commit()

                # Enqueue child links
                for link in _extract_links(html, url):
                    if _same_domain(start_url, link) and link not in visited:
                        queue.append(link)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Failed to scrape %s: %s", url, exc)
                errors.append(f"{url}: {exc}")
                continue

    # Finalise job
    async with AsyncSessionLocal() as session:
        job_row = await session.get(ScrapeJob, uuid.UUID(job_id))
        if job_row:
            job_row.status = "completed" if not errors else "completed_with_errors"
            job_row.pages_scraped = pages_scraped
            job_row.pages_found = len(visited)
            job_row.bytes_scraped = bytes_scraped
            job_row.finished_at = datetime.now(UTC)
            if errors:
                job_row.error = f"{len(errors)} page(s) failed. First: {errors[0]}"
            await session.commit()

    logger.info("Scrape job %s finished: %d pages ingested", job_id, pages_scraped)
