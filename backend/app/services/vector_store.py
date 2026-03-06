"""ChromaDB vector store service — embed, store, and retrieve document chunks."""

import logging
import uuid
from typing import Any

import chromadb
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "jamf_knowledge"
CHUNK_SIZE = 800        # characters per chunk
CHUNK_OVERLAP = 100     # overlap between chunks


async def _get_chroma_client() -> chromadb.AsyncHttpClient:
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


async def _embed(texts: list[str]) -> list[list[float]]:
    """Call Ollama /api/embeddings for a batch of texts."""
    settings = get_settings()
    embeddings: list[list[float]] = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for text in texts:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/embeddings",
                json={"model": settings.embedding_model_name, "prompt": text},
            )
            resp.raise_for_status()
            embeddings.append(resp.json()["embedding"])
    return embeddings


async def ingest_document(
    source_url: str,
    title: str,
    text: str,
) -> tuple[int, list[str]]:
    """
    Chunk, embed, and store a document in ChromaDB.
    Returns (chunk_count, chroma_ids).
    """
    chunks = _chunk_text(text)
    if not chunks:
        return 0, []

    try:
        embeddings = await _embed(chunks)
    except Exception as exc:
        logger.error("Embedding failed for %s: %s", source_url, exc)
        raise

    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas: list[dict[str, Any]] = [
        {"source": source_url, "title": title, "chunk_index": i}
        for i in range(len(chunks))
    ]

    client = await _get_chroma_client()
    collection = await client.get_or_create_collection(COLLECTION_NAME)
    await collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=chunks,
        metadatas=metadatas,
    )
    logger.info("Ingested %d chunks from %s", len(chunks), source_url)
    return len(chunks), ids


async def query_similar(query: str, n_results: int = 5) -> list[dict[str, Any]]:
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
        collection = await client.get_or_create_collection(COLLECTION_NAME)
        results = await collection.query(
            query_embeddings=[embeddings[0]],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.warning("ChromaDB query failed: %s", exc)
        return []

    hits: list[dict[str, Any]] = []
    if results and results.get("documents"):
        for doc, meta in zip(results["documents"][0], results["metadatas"][0], strict=False):
            hits.append({"text": doc, "source": meta.get("source", ""), "title": meta.get("title", "")})
    return hits


async def delete_by_source(source_url: str) -> int:
    """Remove all chunks for a given source URL. Returns count deleted."""
    try:
        client = await _get_chroma_client()
        collection = await client.get_or_create_collection(COLLECTION_NAME)
        results = await collection.get(where={"source": source_url}, include=["documents"])
        ids = results.get("ids", [])
        if ids:
            await collection.delete(ids=ids)
        return len(ids)
    except Exception as exc:
        logger.error("Failed to delete chunks for %s: %s", source_url, exc)
        return 0
