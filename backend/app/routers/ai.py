"""AI assistant router — calls local Ollama for chat completions."""

import logging

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.dependencies import CurrentUser
from app.models.device import Device
from app.models.patch import PatchTitle
from app.models.policy import Policy
from app.models.server import JamfServer
from app.models.smart_group import SmartGroup

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])

SYSTEM_PROMPT = """You are a helpful assistant for a Jamf Pro monitoring dashboard.
You have access to live summary statistics about the managed environment (provided below).
Answer questions about devices, policies, patch management, compliance, and Jamf Pro configuration.
Be concise and precise. If you don't know something, say so rather than guessing.
Do not invent device names, serial numbers, or policy details that are not in the data provided."""


class ChatRequest(BaseModel):
    message: str
    server_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    sources: list[str] = []


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


@router.post("/chat", response_model=ChatResponse)
async def chat(_: CurrentUser, body: ChatRequest) -> ChatResponse:
    settings = get_settings()
    context = await _get_context_stats()

    messages = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{context}"},
        {"role": "user", "content": body.message},
    ]

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": settings.llm_temperature},
                },
            )
            response.raise_for_status()
            data = response.json()
            reply = data["message"]["content"]
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

    return ChatResponse(reply=reply, sources=[])
