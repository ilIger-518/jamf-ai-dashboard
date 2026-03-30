"""ChromaDB vector store service — embed, store, and retrieve document chunks."""

import logging
import uuid
from typing import Any

import chromadb

from app.config import get_settings
from app.services.llm import embed_texts

logger = logging.getLogger(__name__)

COLLECTION_NAME = "jamf_knowledge"
CHUNK_SIZE = 800  # characters per chunk
CHUNK_OVERLAP = 100  # overlap between chunks


async def _get_chroma_client() -> Any:
    settings = get_settings()
    return await chromadb.AsyncHttpClient(
        host=settings.chroma_host,
        port=settings.chroma_port,
    )


def _chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c.strip() for c in chunks if c.strip()]


async def _embed(texts: list[str], num_thread: int | None = None) -> list[list[float]]:
    """Call the configured embedding provider for a batch of texts."""
    return await embed_texts(texts, num_thread=num_thread)


async def ingest_document(
    source_url: str,
    title: str,
    text: str,
    num_thread: int | None = None,
    collection_name: str = COLLECTION_NAME,
) -> tuple[int, list[str]]:
    """
    Chunk, embed, and store a document in ChromaDB.
    Returns (chunk_count, chroma_ids).
    """
    chunks = _chunk_text(text)
    if not chunks:
        return 0, []

    # Replace prior embeddings for the same source so retries/continuations do not duplicate chunks.
    await delete_by_source(source_url, collection_name=collection_name)

    try:
        embeddings = await _embed(chunks, num_thread=num_thread)
    except Exception as exc:
        logger.error("Embedding failed for %s: %s", source_url, exc)
        raise

    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas: list[dict[str, Any]] = [
        {"source": source_url, "title": title, "chunk_index": i} for i in range(len(chunks))
    ]

    client = await _get_chroma_client()
    collection = await client.get_or_create_collection(collection_name)
    await collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=chunks,
        metadatas=metadatas,
    )
    logger.info(
        "Ingested %d chunks from %s into collection %s", len(chunks), source_url, collection_name
    )
    return len(chunks), ids


async def query_similar(
    query: str,
    n_results: int = 5,
    collection_name: str = COLLECTION_NAME,
) -> list[dict[str, Any]]:
    """
    Embed a query and retrieve the top-n similar chunks from ChromaDB.
    Returns list of {text, source, title}.
    """
    try:
        embeddings = await _embed([query])
    except Exception as exc:
        logger.warning("Could not embed query for RAG: %s", exc)
        return []

    try:
        client = await _get_chroma_client()
        collection = await client.get_or_create_collection(collection_name)
        results = await collection.query(
            query_embeddings=[embeddings[0]],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.warning("ChromaDB query failed for collection %s: %s", collection_name, exc)
        return []

    hits: list[dict[str, Any]] = []
    if results and results.get("documents"):
        for doc, meta in zip(results["documents"][0], results["metadatas"][0], strict=False):
            hits.append(
                {"text": doc, "source": meta.get("source", ""), "title": meta.get("title", "")}
            )
    return hits


async def query_similar_multi(
    query: str,
    collection_names: list[str],
    n_results: int = 5,
) -> list[dict[str, Any]]:
    """
    Query multiple collections in priority order and return merged hits.
    Duplicate sources are de-duplicated while preserving first-hit order.
    """
    hits: list[dict[str, Any]] = []
    seen_sources: set[str] = set()

    for collection_name in collection_names:
        collection_hits = await query_similar(
            query,
            n_results=n_results,
            collection_name=collection_name,
        )
        for hit in collection_hits:
            source = str(hit.get("source") or "")
            if source and source in seen_sources:
                continue
            if source:
                seen_sources.add(source)
            hits.append(hit)
            if len(hits) >= n_results:
                return hits

    return hits


async def delete_by_source(source_url: str, collection_name: str = COLLECTION_NAME) -> int:
    """Remove all chunks for a given source URL. Returns count deleted."""
    try:
        client = await _get_chroma_client()
        collection = await client.get_or_create_collection(collection_name)
        results = await collection.get(where={"source": source_url}, include=["documents"])
        ids = results.get("ids", [])
        if ids:
            await collection.delete(ids=ids)
        return len(ids)
    except Exception as exc:
        logger.error("Failed to delete chunks for %s in %s: %s", source_url, collection_name, exc)
        return 0


async def get_source_chunks(
    source_url: str,
    *,
    collection_name: str = COLLECTION_NAME,
    limit: int = 12,
) -> list[str]:
    """Return ordered chunks for a source URL to build a readable text preview."""
    safe_limit = max(1, min(limit, 50))
    try:
        client = await _get_chroma_client()
        collection = await client.get_or_create_collection(collection_name)
        results = await collection.get(
            where={"source": source_url}, include=["documents", "metadatas"]
        )

        documents = results.get("documents") or []
        metadatas = results.get("metadatas") or []
        ordered: list[tuple[int, str]] = []

        for doc, meta in zip(documents, metadatas, strict=False):
            if not isinstance(doc, str) or not doc.strip():
                continue
            idx = 0
            if isinstance(meta, dict):
                raw_idx = meta.get("chunk_index")
                if isinstance(raw_idx, int):
                    idx = raw_idx
            ordered.append((idx, doc.strip()))

        ordered.sort(key=lambda item: item[0])
        return [doc for _, doc in ordered[:safe_limit]]
    except Exception as exc:
        logger.warning("Failed to fetch chunks for %s in %s: %s", source_url, collection_name, exc)
        return []
