"""AI assistant router — per-user chat sessions with full history, persisted to PostgreSQL."""

import logging
import json
import re
import uuid as uuid_lib
from datetime import UTC, datetime
from threading import Lock
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.dependencies import CurrentUser, get_user_permissions
from app.models.ai import ChatMessage, ChatSession
from app.models.device import Device
from app.models.patch import PatchTitle
from app.models.policy import Policy
from app.models.server import JamfServer
from app.models.smart_group import SmartGroup
from app.services.encryption import decrypt
from app.services.vector_store import query_similar

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])

_PENDING_ACTIONS: dict[str, dict] = {}
_PENDING_ACTIONS_LOCK = Lock()

SYSTEM_PROMPT = """You are a helpful assistant for a Jamf Pro monitoring dashboard.
You have access to live summary statistics about the managed environment and, when available,
relevant documentation retrieved from the knowledge base.
Answer questions about devices, policies, patch management, compliance, and Jamf Pro configuration.
Be concise and precise. If you don't know something, say so rather than guessing.
Do not invent device names, serial numbers, or policy details that are not in the data provided."""

POLICY_PROMPT = """You are Jamf Policy and Group Builder AI.
You can do three things:
1) Explain policy and group concepts with safe defaults.
2) Create Jamf policies when the user asks to create one.
3) Create Jamf computer groups (smart or static) when requested.

When a policy creation request is ambiguous, ask one concise clarification question.
Keep answers concise and operational.
"""


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
    bot_mode: Literal["rag_readonly", "policy_builder"] = "rag_readonly"
    target_server_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    sources: list[str] = []


def _ndjson_event(payload: dict) -> bytes:
    return (json.dumps(payload, ensure_ascii=True) + "\n").encode("utf-8")


def _looks_like_policy_create_intent(message: str) -> bool:
    msg = message.lower()
    return ("policy" in msg) and any(k in msg for k in ["create", "make", "build", "new"])


def _looks_like_group_create_intent(message: str) -> bool:
    msg = message.lower()
    has_group = "group" in msg or "computer group" in msg
    has_verb = any(k in msg for k in ["create", "make", "build", "new"])
    return has_group and has_verb


def _looks_like_script_create_intent(message: str) -> bool:
    msg = message.lower()
    has_script = "script" in msg
    has_verb = any(k in msg for k in ["create", "make", "build", "new"])
    return has_script and has_verb


def _is_approval_intent(message: str) -> bool:
    msg = message.strip().lower()
    return msg in {
        "approve",
        "confirm",
        "yes",
        "yes, approve",
        "yes approve",
        "run it",
        "execute",
        "go ahead",
    }


def _is_cancel_intent(message: str) -> bool:
    msg = message.strip().lower()
    return msg in {"cancel", "stop", "abort", "never mind", "nevermind"}


def _pending_key(user_id: object, session_id: str) -> str:
    return f"{user_id}:{session_id}"


def _set_pending_action(user_id: object, session_id: str, action: dict) -> None:
    with _PENDING_ACTIONS_LOCK:
        _PENDING_ACTIONS[_pending_key(user_id, session_id)] = action


def _peek_pending_action(user_id: object, session_id: str) -> dict | None:
    with _PENDING_ACTIONS_LOCK:
        return _PENDING_ACTIONS.get(_pending_key(user_id, session_id))


def _pop_pending_action(user_id: object, session_id: str) -> dict | None:
    with _PENDING_ACTIONS_LOCK:
        return _PENDING_ACTIONS.pop(_pending_key(user_id, session_id), None)


def _clear_pending_action(user_id: object, session_id: str) -> None:
    with _PENDING_ACTIONS_LOCK:
        _PENDING_ACTIONS.pop(_pending_key(user_id, session_id), None)


def _extract_json_object(content: str) -> dict | None:
    match = re.search(r"\{[\s\S]*\}", content)
    raw = match.group(0) if match else content
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def _policy_spec_from_prompt(message: str) -> dict:
    """Ask Ollama to produce a minimal policy spec as JSON."""
    settings = get_settings()
    prompt = (
        "Return ONLY JSON. No markdown.\n"
        "Generate a Jamf policy draft from this request.\n"
        "Fields: name (string), enabled (bool), trigger (EVENT|LOGIN|STARTUP), "
        "frequency (Once per computer|Ongoing), trigger_other (string), notes (string).\n"
        f"User request: {message}"
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.1},
            },
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"].strip()

    parsed = _extract_json_object(content)
    if parsed is None:
        fallback_name = message.strip()[:80] or "Jamf AI Policy"
        return {
            "name": fallback_name,
            "enabled": True,
            "trigger": "EVENT",
            "frequency": "Once per computer",
            "trigger_other": "jamf-ai-policy",
            "notes": "Generated by Jamf AI Policy Builder",
        }

    name = (parsed.get("name") or "Jamf AI Policy").strip()[:128]
    trigger = (parsed.get("trigger") or "EVENT").upper()
    if trigger not in {"EVENT", "LOGIN", "STARTUP"}:
        trigger = "EVENT"
    frequency = parsed.get("frequency") or "Once per computer"
    if frequency not in {"Once per computer", "Ongoing"}:
        frequency = "Once per computer"
    trigger_other = (parsed.get("trigger_other") or "jamf-ai-policy").strip()[:64]
    notes = (parsed.get("notes") or "Generated by Jamf AI Policy Builder").strip()[:1024]
    enabled = bool(parsed.get("enabled", True))

    return {
        "name": name,
        "enabled": enabled,
        "trigger": trigger,
        "frequency": frequency,
        "trigger_other": trigger_other,
        "notes": notes,
    }


async def _group_spec_from_prompt(message: str) -> dict:
    """Ask Ollama to produce a minimal group spec as JSON."""
    settings = get_settings()
    prompt = (
        "Return ONLY JSON. No markdown.\n"
        "Generate a Jamf computer group draft from this request.\n"
        "Fields: name (string), group_type (smart|static), notes (string), "
        "criteria_value (string, optional for smart groups).\n"
        f"User request: {message}"
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.1},
            },
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"].strip()

    parsed = _extract_json_object(content)
    fallback_name = message.strip()[:80] or "Jamf AI Group"
    if parsed is None:
        return {
            "name": fallback_name,
            "group_type": "static",
            "notes": "Generated by Jamf AI Policy and Group Builder",
            "criteria_value": "",
        }

    name = (parsed.get("name") or fallback_name).strip()[:128]
    group_type = str(parsed.get("group_type") or "static").strip().lower()
    if group_type not in {"smart", "static"}:
        group_type = "smart" if "smart" in message.lower() else "static"
    notes = (
        str(parsed.get("notes") or "Generated by Jamf AI Policy and Group Builder")
        .strip()[:1024]
    )
    criteria_value = str(parsed.get("criteria_value") or "").strip()[:128]
    return {
        "name": name,
        "group_type": group_type,
        "notes": notes,
        "criteria_value": criteria_value,
    }


async def _script_spec_from_prompt(message: str) -> dict:
    """Ask Ollama to produce a minimal script spec as JSON."""
    settings = get_settings()
    prompt = (
        "Return ONLY JSON. No markdown.\n"
        "Generate a Jamf script draft from this request.\n"
        "Fields: name (string), script_contents (string), notes (string), info (string), priority (Before|After).\n"
        f"User request: {message}"
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.1},
            },
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"].strip()

    parsed = _extract_json_object(content)
    fallback_name = message.strip()[:80] or "Jamf AI Script"
    if parsed is None:
        return {
            "name": fallback_name,
            "script_contents": "#!/bin/bash\n\nexit 0\n",
            "notes": "Generated by Jamf AI Policy and Group Builder",
            "info": "Generated by Jamf AI",
            "priority": "After",
        }

    name = (str(parsed.get("name") or fallback_name)).strip()[:128]
    script_contents = str(parsed.get("script_contents") or "#!/bin/bash\n\nexit 0\n")
    if not script_contents.startswith("#!"):
        script_contents = "#!/bin/bash\n" + script_contents
    notes = str(parsed.get("notes") or "Generated by Jamf AI").strip()[:1024]
    info = str(parsed.get("info") or "Generated by Jamf AI").strip()[:1024]
    priority = str(parsed.get("priority") or "After").strip()
    if priority not in {"Before", "After"}:
        priority = "After"
    return {
        "name": name,
        "script_contents": script_contents,
        "notes": notes,
        "info": info,
        "priority": priority,
    }


async def _resolve_target_server(target_server_id: str | None) -> JamfServer | None:
    async with AsyncSessionLocal() as db:
        query = select(JamfServer).where(JamfServer.is_active.is_(True)).order_by(JamfServer.name.asc())
        if target_server_id:
            query = select(JamfServer).where(JamfServer.id == uuid_lib.UUID(target_server_id))
        result = await db.execute(query)
        return result.scalar_one_or_none()


def _format_preview(action: dict) -> str:
    base_url = action["base_url"]
    endpoint = action["endpoint"]
    payload = action["body"]
    kind = action["kind"]
    server_name = action["server_name"]
    body_json = json.dumps(payload, ensure_ascii=True, indent=2)
    return (
        f"Planned {kind} create on {server_name}.\n"
        "API command preview (not executed yet):\n"
        "```bash\n"
        f"curl -X POST '{base_url}{endpoint}' \\\n+  -H 'Authorization: Bearer <ACCESS_TOKEN>' \\\n+  -H 'Accept: application/json' \\\n+  -H 'Content-Type: application/json' \\\n+  -d '{body_json}'\n"
        "```\n"
        "Reply with `approve` to execute or `cancel` to discard."
    )


async def _build_action_plan(
    message: str,
    current_user,
    target_server_id: str | None,
) -> dict | None:
    permissions = get_user_permissions(current_user)
    if "servers.manage" not in permissions and not current_user.is_admin:
        return {
            "error": "You do not have permission to create objects. Required: servers.manage"
        }

    if not (
        _looks_like_policy_create_intent(message)
        or _looks_like_group_create_intent(message)
        or _looks_like_script_create_intent(message)
    ):
        return None

    server = await _resolve_target_server(target_server_id)
    if not server:
        return {"error": "No target Jamf server found. Select a server and try again."}

    base_url = server.url.rstrip("/")

    if _looks_like_script_create_intent(message):
        spec = await _script_spec_from_prompt(message)
        return {
            "kind": "script",
            "server_id": str(server.id),
            "server_name": server.name,
            "base_url": base_url,
            "endpoint": "/JSSResource/scripts/id/0",
            "body": {"script": spec},
        }

    if _looks_like_policy_create_intent(message):
        spec = await _policy_spec_from_prompt(message)
        return {
            "kind": "policy",
            "server_id": str(server.id),
            "server_name": server.name,
            "base_url": base_url,
            "endpoint": "/JSSResource/policies/id/0",
            "body": {
                "policy": {
                    "general": {
                        "name": spec["name"],
                        "enabled": spec["enabled"],
                        "trigger": spec["trigger"],
                        "trigger_other": spec["trigger_other"],
                        "frequency": spec["frequency"],
                        "notes": spec["notes"],
                    },
                    "scope": {"all_computers": False},
                    "self_service": {"use_for_self_service": False},
                }
            },
        }

    spec = await _group_spec_from_prompt(message)
    if spec["group_type"] == "smart":
        body = {
            "computer_group": {
                "name": spec["name"],
                "is_smart": True,
                "criteria": {
                    "criterion": [
                        {
                            "name": "Computer Name",
                            "priority": 0,
                            "and_or": "and",
                            "search_type": "like",
                            "value": spec["criteria_value"] or "-",
                        }
                    ]
                },
            }
        }
    else:
        body = {
            "computer_group": {
                "name": spec["name"],
                "is_smart": False,
                "computers": {"computer": []},
            }
        }
    return {
        "kind": "group",
        "group_type": spec["group_type"],
        "server_id": str(server.id),
        "server_name": server.name,
        "base_url": base_url,
        "endpoint": "/JSSResource/computergroups/id/0",
        "body": body,
    }


async def _execute_action_plan(current_user, action: dict) -> str:
    permissions = get_user_permissions(current_user)
    if "servers.manage" not in permissions and not current_user.is_admin:
        return "You do not have permission to create objects. Required: servers.manage"

    server = await _resolve_target_server(action.get("server_id"))
    if not server:
        return "Target server no longer exists."

    base_url = server.url.rstrip("/")
    client_id = decrypt(server.client_id)
    client_secret = decrypt(server.client_secret)

    async with httpx.AsyncClient(timeout=30.0) as client:
        token = await _oauth_token(client, base_url, client_id, client_secret)
        if not token:
            return "Execution failed: OAuth token error."

        resp = await client.post(
            f"{base_url}{action['endpoint']}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=action["body"],
        )
        if resp.status_code not in (200, 201):
            return (
                f"{action['kind'].capitalize()} create failed on {server.name} "
                f"({resp.status_code}): {resp.text[:300]}"
            )

    if action["kind"] == "group":
        kind_label = f"{action.get('group_type', 'static')} group"
        group_name = (action["body"].get("computer_group") or {}).get("name", "Unnamed Group")
        return f"Created {kind_label} on {server.name}: '{group_name}'."
    if action["kind"] == "policy":
        policy_name = (((action["body"].get("policy") or {}).get("general") or {}).get("name", "Unnamed Policy"))
        return f"Created policy on {server.name}: '{policy_name}'."
    script_name = (action["body"].get("script") or {}).get("name", "Unnamed Script")
    return f"Created script on {server.name}: '{script_name}'."


async def _oauth_token(client: httpx.AsyncClient, base_url: str, client_id: str, client_secret: str) -> str | None:
    token_resp = await client.post(
        f"{base_url}/api/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if token_resp.status_code not in (200, 201):
        return None
    return token_resp.json().get("access_token")


async def _create_policy_on_server(
    message: str,
    current_user,
    target_server_id: str | None,
) -> str:
    permissions = get_user_permissions(current_user)
    if "servers.manage" not in permissions and not current_user.is_admin:
        return "You do not have permission to create policies. Required: servers.manage"

    server = await _resolve_target_server(target_server_id)

    if not server:
        return "No target Jamf server found. Select a server and try again."

    spec = await _policy_spec_from_prompt(message)

    base_url = server.url.rstrip("/")
    client_id = decrypt(server.client_id)
    client_secret = decrypt(server.client_secret)

    async with httpx.AsyncClient(timeout=30.0) as client:
        token = await _oauth_token(client, base_url, client_id, client_secret)
        if not token:
            return "Policy create failed: OAuth token error."
        payload = {
            "policy": {
                "general": {
                    "name": spec["name"],
                    "enabled": spec["enabled"],
                    "trigger": spec["trigger"],
                    "trigger_other": spec["trigger_other"],
                    "frequency": spec["frequency"],
                    "notes": spec["notes"],
                },
                "scope": {"all_computers": False},
                "self_service": {"use_for_self_service": False},
            }
        }
        create_resp = await client.post(
            f"{base_url}/JSSResource/policies/id/0",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if create_resp.status_code not in (200, 201):
            return (
                "Policy create failed on Jamf target "
                f"{server.name} ({create_resp.status_code}): {create_resp.text[:300]}"
            )

    return (
        f"Policy created on {server.name}: '{spec['name']}' "
        f"(trigger={spec['trigger']}, frequency={spec['frequency']})."
    )


async def _create_group_on_server(
    message: str,
    current_user,
    target_server_id: str | None,
) -> str:
    permissions = get_user_permissions(current_user)
    if "servers.manage" not in permissions and not current_user.is_admin:
        return "You do not have permission to create groups. Required: servers.manage"

    server = await _resolve_target_server(target_server_id)
    if not server:
        return "No target Jamf server found. Select a server and try again."

    spec = await _group_spec_from_prompt(message)
    base_url = server.url.rstrip("/")
    client_id = decrypt(server.client_id)
    client_secret = decrypt(server.client_secret)

    async with httpx.AsyncClient(timeout=30.0) as client:
        token = await _oauth_token(client, base_url, client_id, client_secret)
        if not token:
            return "Group create failed: OAuth token error."

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        endpoint = f"{base_url}/JSSResource/computergroups/id/0"

        # Smart groups require criteria. If none is available, we fall back to static.
        wants_smart = spec["group_type"] == "smart"
        if wants_smart:
            criteria_value = spec["criteria_value"] or "-"
            smart_payload = {
                "computer_group": {
                    "name": spec["name"],
                    "is_smart": True,
                    "criteria": {
                        "criterion": [
                            {
                                "name": "Computer Name",
                                "priority": 0,
                                "and_or": "and",
                                "search_type": "like",
                                "value": criteria_value,
                            }
                        ]
                    },
                }
            }
            smart_resp = await client.post(endpoint, headers=headers, json=smart_payload)
            if smart_resp.status_code in (200, 201):
                return f"Smart group created on {server.name}: '{spec['name']}'."

        static_payload = {
            "computer_group": {
                "name": spec["name"],
                "is_smart": False,
                "computers": {"computer": []},
            }
        }
        static_resp = await client.post(endpoint, headers=headers, json=static_payload)
        if static_resp.status_code not in (200, 201):
            return (
                "Group create failed on Jamf target "
                f"{server.name} ({static_resp.status_code}): {static_resp.text[:300]}"
            )

    if spec["group_type"] == "smart":
        return (
            f"Static group created on {server.name}: '{spec['name']}'. "
            "Smart group creation was requested, but static fallback was applied."
        )
    return f"Static group created on {server.name}: '{spec['name']}'."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_context_stats() -> str:
    """Pull live aggregate stats from the DB to ground the LLM response."""
    try:
        async with AsyncSessionLocal() as session:
            total_devices = (
                await session.execute(select(func.count()).select_from(Device))
            ).scalar_one()
            managed_devices = (
                await session.execute(
                    select(func.count()).select_from(Device).where(Device.is_managed.is_(True))
                )
            ).scalar_one()
            total_policies = (
                await session.execute(select(func.count()).select_from(Policy))
            ).scalar_one()
            enabled_policies = (
                await session.execute(
                    select(func.count()).select_from(Policy).where(Policy.enabled.is_(True))
                )
            ).scalar_one()
            total_patches = (
                await session.execute(select(func.count()).select_from(PatchTitle))
            ).scalar_one()
            unpatched = (
                await session.execute(
                    select(func.sum(PatchTitle.unpatched_count)).select_from(PatchTitle)
                )
            ).scalar_one() or 0
            total_groups = (
                await session.execute(select(func.count()).select_from(SmartGroup))
            ).scalar_one()
            total_servers = (
                await session.execute(select(func.count()).select_from(JamfServer))
            ).scalar_one()

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
        # Large prompts and policy generation can take longer than default HTTP timeouts.
        async with httpx.AsyncClient(timeout=float(settings.llm_timeout_seconds)) as client:
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
            payload = response.json()
            message = payload.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str):
                logger.error("Unexpected Ollama response payload: %s", payload)
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Ollama returned an unexpected response payload. "
                        "Check backend logs and verify the selected model can answer chat requests."
                    ),
                )
            return content
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Ollama is not reachable at {settings.ollama_base_url}. "
                "Make sure the Ollama container is running and the model is pulled."
            ),
        )
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=504,
            detail=(
                "The AI model took too long to respond. "
                "Try a shorter prompt, or increase LLM_TIMEOUT_SECONDS."
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
    except ValueError as exc:
        logger.exception("Invalid Ollama JSON response: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Ollama returned invalid JSON. Check backend logs.",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected AI error: %s", exc)
        raise HTTPException(status_code=500, detail="Unexpected error calling the AI service.")


async def _stream_ollama(history: list[dict]):
    """Stream incremental text chunks from Ollama."""
    settings = get_settings()
    timeout = httpx.Timeout(
        connect=10.0,
        read=float(settings.llm_timeout_seconds),
        write=30.0,
        pool=30.0,
    )
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": history,
                    "stream": True,
                    "options": {"temperature": settings.llm_temperature},
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    evt = json.loads(line)
                    if not isinstance(evt, dict):
                        logger.error("Unexpected Ollama stream event payload: %s", evt)
                        raise HTTPException(
                            status_code=502,
                            detail="Ollama returned an invalid stream event. Check backend logs.",
                        )
                    chunk = (evt.get("message") or {}).get("content") or ""
                    if chunk:
                        yield chunk
                    if evt.get("done"):
                        break
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Ollama is not reachable at {settings.ollama_base_url}. "
                "Make sure the Ollama container is running and the model is pulled."
            ),
        )
    except httpx.ReadTimeout:
        raise HTTPException(
            status_code=504,
            detail=(
                "The AI model took too long to respond. "
                "Try a shorter prompt, or increase LLM_TIMEOUT_SECONDS."
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
    except ValueError as exc:
        logger.exception("Invalid Ollama stream JSON response: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Ollama returned invalid JSON while streaming. Check backend logs.",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected AI stream error: %s", exc)
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
    bot_mode = body.bot_mode

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
        system_prompt = POLICY_PROMPT if bot_mode == "policy_builder" else SYSTEM_PROMPT
        ollama_messages: list[dict] = [
            {"role": "system", "content": f"{system_prompt}\n\n{context}{rag_context}"},
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

    # Builder mode requires explicit approval before execution.
    reply: str
    if bot_mode == "policy_builder":
        pending = _peek_pending_action(current_user.id, session_id_str)
        if pending and _is_cancel_intent(body.message):
            _clear_pending_action(current_user.id, session_id_str)
            reply = "Canceled pending action."
        elif pending and _is_approval_intent(body.message):
            approved = _pop_pending_action(current_user.id, session_id_str)
            if approved is None:
                reply = "No pending action found."
            else:
                reply = await _execute_action_plan(current_user, approved)
        else:
            plan = await _build_action_plan(body.message, current_user, body.target_server_id)
            if plan and plan.get("error"):
                reply = str(plan["error"])
            elif plan:
                _set_pending_action(current_user.id, session_id_str, plan)
                reply = _format_preview(plan)
            else:
                # Normal conversation when no create action is requested.
                reply = await _call_ollama(ollama_messages)
    else:
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


@router.post("/chat/stream")
async def chat_stream(current_user: CurrentUser, body: ChatRequest) -> StreamingResponse:
    """Stream chat progress and final response as NDJSON events."""

    async def event_stream():
        try:
            yield _ndjson_event({"type": "stage", "message": "Gathering environment context..."})
            context = await _get_context_stats()
            bot_mode = body.bot_mode

            yield _ndjson_event({"type": "stage", "message": "Searching knowledge base..."})
            rag_chunks = await query_similar(body.message, n_results=5)
            sources: list[str] = []
            rag_context = ""
            if rag_chunks:
                rag_context = "\n\nRelevant documentation from the knowledge base:\n"
                for chunk in rag_chunks:
                    rag_context += f"\n---\nSource: {chunk['source']}\n{chunk['text']}\n"
                    if chunk["source"] not in sources:
                        sources.append(chunk["source"])

            yield _ndjson_event({"type": "stage", "message": "Loading session history..."})
            async with AsyncSessionLocal() as db:
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
                        yield _ndjson_event({"type": "error", "message": "Session not found"})
                        return
                else:
                    session_obj = ChatSession(user_id=current_user.id, title="New Chat")
                    db.add(session_obj)
                    await db.flush()

                prior_result = await db.execute(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_obj.id)
                    .order_by(ChatMessage.created_at.asc())
                )
                prior_messages = prior_result.scalars().all()

                system_prompt = POLICY_PROMPT if bot_mode == "policy_builder" else SYSTEM_PROMPT
                ollama_messages: list[dict] = [
                    {"role": "system", "content": f"{system_prompt}\n\n{context}{rag_context}"},
                ]
                for pm in prior_messages:
                    ollama_messages.append({"role": pm.role, "content": pm.content})
                ollama_messages.append({"role": "user", "content": body.message})

                user_msg = ChatMessage(session_id=session_obj.id, role="user", content=body.message)
                db.add(user_msg)
                await db.flush()

                if len(prior_messages) == 0:
                    session_obj.title = body.message[:60].strip()

                await db.commit()
                session_id_str = str(session_obj.id)

            if bot_mode == "policy_builder":
                pending = _peek_pending_action(current_user.id, session_id_str)
                if pending and _is_cancel_intent(body.message):
                    _clear_pending_action(current_user.id, session_id_str)
                    reply = "Canceled pending action."
                elif pending and _is_approval_intent(body.message):
                    yield _ndjson_event({"type": "stage", "message": "Executing approved action..."})
                    approved = _pop_pending_action(current_user.id, session_id_str)
                    if approved is None:
                        reply = "No pending action found."
                    else:
                        reply = await _execute_action_plan(current_user, approved)
                else:
                    plan = await _build_action_plan(body.message, current_user, body.target_server_id)
                    if plan and plan.get("error"):
                        reply = str(plan["error"])
                    elif plan:
                        _set_pending_action(current_user.id, session_id_str, plan)
                        reply = _format_preview(plan)
                    else:
                        yield _ndjson_event({"type": "stage", "message": "Generating response..."})
                        reply_parts: list[str] = []
                        word_buffer = ""
                        async for chunk in _stream_ollama(ollama_messages):
                            reply_parts.append(chunk)
                            word_buffer += chunk
                            tokens = re.findall(r"\s*\S+\s*", word_buffer)
                            if tokens and word_buffer and not word_buffer[-1].isspace():
                                tokens = tokens[:-1]
                            consumed = "".join(tokens)
                            if consumed:
                                for token in tokens:
                                    yield _ndjson_event({"type": "delta", "content": token})
                                word_buffer = word_buffer[len(consumed):]
                        if word_buffer:
                            yield _ndjson_event({"type": "delta", "content": word_buffer})
                        reply = "".join(reply_parts)
            else:
                yield _ndjson_event({"type": "stage", "message": "Generating response..."})
                reply_parts: list[str] = []
                word_buffer = ""
                async for chunk in _stream_ollama(ollama_messages):
                    reply_parts.append(chunk)
                    word_buffer += chunk
                    tokens = re.findall(r"\s*\S+\s*", word_buffer)
                    if tokens and word_buffer and not word_buffer[-1].isspace():
                        tokens = tokens[:-1]
                    consumed = "".join(tokens)
                    if consumed:
                        for token in tokens:
                            yield _ndjson_event({"type": "delta", "content": token})
                        word_buffer = word_buffer[len(consumed):]
                if word_buffer:
                    yield _ndjson_event({"type": "delta", "content": word_buffer})
                reply = "".join(reply_parts)

            yield _ndjson_event({"type": "stage", "message": "Saving response..."})
            async with AsyncSessionLocal() as db:
                sources_payload = [{"source": s} for s in sources]
                assistant_msg = ChatMessage(
                    session_id=uuid_lib.UUID(session_id_str),
                    role="assistant",
                    content=reply,
                    sources=sources_payload if sources_payload else None,
                )
                db.add(assistant_msg)

                sess = await db.get(ChatSession, uuid_lib.UUID(session_id_str))
                if sess:
                    sess.updated_at = datetime.now(UTC)

                await db.commit()

            yield _ndjson_event(
                {
                    "type": "final",
                    "session_id": session_id_str,
                    "reply": reply,
                    "sources": sources,
                }
            )
        except HTTPException as exc:
            yield _ndjson_event(
                {
                    "type": "error",
                    "message": str(exc.detail) if exc.detail else "AI request failed.",
                }
            )
        except Exception:
            logger.exception("Unexpected streaming AI error")
            yield _ndjson_event(
                {
                    "type": "error",
                    "message": "Unexpected error calling the AI service.",
                }
            )

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
