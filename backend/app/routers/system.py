"""System info and software-update proxy endpoints."""

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.dependencies import AdminUser

router = APIRouter(prefix="/system", tags=["system"])


class UpdaterConfigPayload(BaseModel):
    repo_url: str
    branch: str = "main"


class DockerLogsResponse(BaseModel):
    service: str | None
    tail: int
    services: list[str]
    logs: str


async def _updater(
    method: str,
    path: str,
    payload: dict | None = None,
    params: dict | None = None,
) -> dict:
    settings = get_settings()
    url = f"{settings.updater_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if method == "GET":
                r = await client.get(url, params=params)
            else:
                r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Updater service unavailable")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Updater error: {exc}")


@router.get("/update/status", summary="Current update check state (admin)")
async def get_update_status(_: AdminUser) -> dict:
    return await _updater("GET", "/status")


@router.get("/update/config", summary="Get updater repository config (admin)")
async def get_update_config(_: AdminUser) -> dict:
    return await _updater("GET", "/config")


@router.post("/update/config", summary="Set updater repository config (admin)")
async def set_update_config(payload: UpdaterConfigPayload, _: AdminUser) -> dict:
    return await _updater("POST", "/config", payload.model_dump())


@router.post("/update/check", summary="Trigger an immediate update check (admin)")
async def trigger_check(_: AdminUser) -> dict:
    return await _updater("POST", "/check")


@router.post("/update/apply", summary="Apply a pending update (admin)")
async def apply_update(_: AdminUser) -> dict:
    return await _updater("POST", "/apply")


@router.get("/docker-logs", response_model=DockerLogsResponse, summary="Get docker compose logs (admin)")
async def get_docker_logs(
    _: AdminUser,
    service: str | None = None,
    tail: int = 400,
) -> dict:
    return await _updater(
        "GET",
        "/docker-logs",
        params={"service": service, "tail": tail},
    )
