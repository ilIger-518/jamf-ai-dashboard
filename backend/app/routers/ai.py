"""AI assistant router — per-user chat sessions with full history, persisted to PostgreSQL."""

import logging
import uuid as uuid_lib
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.dependencies import CurrentUser
from app.models.ai import ChatMessage, ChatSession
from app.models.device import Device
from app.models.patch import PatchTitle
from app.models.policy import Policy
from app.models.server import JamfServer
from app.models.smart_group import SmartGroup
from app.services.vector_store import query_similar

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])

SYSTEM_PROMPT = """You are a helpful assistant for a Jamf Pro monitoring dashboard.
You have access to live summary statistics about the managed environment and, when available,
relevant documentation retrieved from the knowledge base.
Answer questions about devices, policies, patch management, compliance, and Jamf Pro configuration.
Be concise and precise. If you don't know something, say so rather than guessing.
Do not invent device names, serial numbers, or policy details that are not in the data provided."""


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SessionCreate(BaseModel):
    title: str = "New Chat"


class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    sources: list[str] = []
    created_at: str

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    sources: list[str] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_context_stats() -> str:
    """Pull live aggregate stats from the DB to ground the LLM response."""
    try:
        async with AsyncSessionLocal() as session:
            total_devices = (await session.execute(select(func.count()).select_from(Device))).scalar_one()
            managed_devices = (
                await session.execute(select(func.count()).select_from(Device).where(Device.is_managed.is_(True)))
            ).scalar_one()
            total_policies = (await session.execute(select(func.count()).select_from(Policy))).scalar_one()
            enabled_policies = (
                await session.execute(select(func.count()).select_from(Policy).where(Policy.enabled.is_(True)))
            ).scalar_one()
            total_patches = (await session.execute(select(func.count()).select_from(PatchTitle))).scalar_one()
            unpatched = (
                await session.execute(
                    select(func.sum(PatchTitle.unpatched_count)).select_from(PatchTitle)
                )
            ).scalar_one() or 0
            total_groups = (await session.execute(select(func.count()).select_from(SmartGroup))).scalar_one()
            total_servers = (await session.execute(select(func.count()).select_from(JamfServer))).scalar_one()

        return (
            f"Current environment summary:\n"
            f"- Jamf servers: {total_servers}\n"
            f"- Total devices: {total_devices} ({managed_devices} managed, {total_devices - managed_devices} unmanaged)\n"
            f"- Policies: {total_policies} ({enabled_policies} enabled)\n"
            f"- Patch titles: {total_patches} (devices with unpatched software: {unpatched})\n"
            f"- Smart groups: {total_groups}"
        )
    except Exception as exc:
        logger.warning("Could not fetch context stats: %s", exc)
        return "No environment data available yet."


async def _call_ollama(history: list[dict]) -> str:
    """Send message history to Ollama and return the reply text."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": history,
                    "stream": False,
                    "options": {"temperature": settings.llm_temperature},
                },
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Ollama is not reachable at {settings.ollama_base_url}. "
                "Make sure the Ollama container is running and the model is pulled."
            ),
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Model '{settings.ollama_model}' is not available. "
                    f"Pull it with: docker exec -it ollama ollama pull {settings.ollama_model}"
                ),
            )
        logger.error("Ollama error: %s — %s", exc.response.status_code, exc.response.text)
        raise HTTPException(status_code=502, detail="Ollama returned an error. Check backend logs.")
    except Exception as exc:
        logger.exception("Unexpected AI error: %s", exc)
        raise HTTPException(status_code=500, detail="Unexpected error calling the AI service.")


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------

@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(current_user: CurrentUser) -> list[SessionResponse]:
    """Return all chat sessions for the current user, newest first."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == current_user.id)
            .order_by(ChatSession.updated_at.desc())
        )
        sessions = result.scalars().all()
    return [
        SessionResponse(
            id=str(s.id),
            title=s.title,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        )
        for s in sessions
    ]


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(current_user: CurrentUser, body: SessionCreate) -> SessionResponse:
    """Create a new empty chat session."""
    async with AsyncSessionLocal() as db:
        session = ChatSession(user_id=current_user.id, title=body.title)
        db.add(session)
        await db.commit()
        await db.refresh(session)
    return SessionResponse(
        id=str(session.id),
        title=session.title,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, current_user: CurrentUser) -> None:
    """Delete a session and all its messages."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == uuid_lib.UUID(session_id),
                ChatSession.user_id == current_user.id,
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        await db.delete(session)
        await db.commit()


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages(session_id: str, current_user: CurrentUser) -> list[MessageResponse]:
    """Return all messages in a session (oldest first)."""
    async with AsyncSessionLocal() as db:
        # Verify session belongs to the current user
        sess_result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == uuid_lib.UUID(session_id),
                ChatSession.user_id == current_user.id,
            )
        )
        if not sess_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Session not found")

        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == uuid_lib.UUID(session_id))
            .order_by(ChatMessage.created_at.asc())
        )
        messages = result.scalars().all()
    return [
        MessageResponse(
            id=str(m.id),
            role=m.role,
            content=m.content,
            sources=[s["source"] for s in (m.sources or []) if "source" in s],
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


# ---------------------------------------------------------------------------
# Chat endpoint — persists messages and maintains multi-turn history
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def chat(current_user: CurrentUser, body: ChatRequest) -> ChatResponse:
    """
    Send a message in a session. If session_id is omitted, a new session is created.
    The full message history is included in the Ollama request for multi-turn context.
    Messages are persisted to the database and scoped to the current user.
    """
    context = await _get_context_stats()

    # RAG: retrieve relevant chunks from the knowledge base
    rag_chunks = await query_similar(body.message, n_results=5)
    sources: list[str] = []
    rag_context = ""
    if rag_chunks:
        rag_context = "\n\nRelevant documentation from the knowledge base:\n"
        for chunk in rag_chunks:
            rag_context += f"\n---\nSource: {chunk['source']}\n{chunk['text']}\n"
            if chunk["source"] not in sources:
                sources.append(chunk["source"])

    async with AsyncSessionLocal() as db:
        # Resolve or create the session
        session_obj: ChatSession | None = None
        if body.session_id:
            result = await db.execute(
                select(ChatSession).where(
                    ChatSession.id == uuid_lib.UUID(body.session_id),
                    ChatSession.user_id == current_user.id,
                )
            )
            session_obj = result.scalar_one_or_none()
            if not session_obj:
                raise HTTPException(status_code=404, detail="Session not found")
        else:
            session_obj = ChatSession(user_id=current_user.id, title="New Chat")
            db.add(session_obj)
            await db.flush()  # get the ID without committing yet

        # Load prior messages for multi-turn history
        prior_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_obj.id)
            .order_by(ChatMessage.created_at.asc())
        )
        prior_messages = prior_result.scalars().all()

        # Build the Ollama message list
        ollama_messages: list[dict] = [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{context}{rag_context}"},
        ]
        for pm in prior_messages:
            ollama_messages.append({"role": pm.role, "content": pm.content})
        ollama_messages.append({"role": "user", "content": body.message})

        # Save the user message
        user_msg = ChatMessage(session_id=session_obj.id, role="user", content=body.message)
        db.add(user_msg)
        await db.flush()

        # Auto-title the session from the first user message (first 60 chars)
        if len(prior_messages) == 0:
            session_obj.title = body.message[:60].strip()

        await db.commit()
        session_id_str = str(session_obj.id)

    # Call Ollama outside the DB transaction (can be slow)
    reply = await _call_ollama(ollama_messages)

    # Persist the assistant reply
    async with AsyncSessionLocal() as db:
        sources_payload = [{"source": s} for s in sources]
        assistant_msg = ChatMessage(
            session_id=uuid_lib.UUID(session_id_str),
            role="assistant",
            content=reply,
            sources=sources_payload if sources_payload else None,
        )
        db.add(assistant_msg)

        # Touch updated_at on the session so it floats to the top of the list
        sess = await db.get(ChatSession, uuid_lib.UUID(session_id_str))
        if sess:
            sess.updated_at = datetime.now(UTC)

        await db.commit()

    return ChatResponse(session_id=session_id_str, reply=reply, sources=sources)
