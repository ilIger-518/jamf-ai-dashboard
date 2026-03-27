"""System info and software-update proxy endpoints."""

import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.responses import FileResponse

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


class AIConfigPayload(BaseModel):
    provider: str
    embedding_provider: str = "local"
    custom_base_url: str = ""
    custom_model: str = ""
    custom_api_key: str = ""
    custom_chat_api_key: str = ""
    custom_scrape_model: str = ""
    custom_scrape_api_key: str = ""
    local_embedding_model: str = ""
    custom_embedding_model: str = ""
    custom_embedding_api_key: str = ""


class AIConfigResponse(BaseModel):
    provider: str
    embedding_provider: str
    ollama_base_url: str
    ollama_model: str
    custom_base_url: str
    custom_model: str
    custom_api_key_set: bool
    custom_api_key_masked: str | None = None
    custom_chat_api_key_set: bool
    custom_chat_api_key_masked: str | None = None
    custom_scrape_model: str
    custom_scrape_api_key_set: bool
    custom_scrape_api_key_masked: str | None = None
    local_embedding_model: str
    custom_embedding_model: str
    custom_embedding_api_key_set: bool
    custom_embedding_api_key_masked: str | None = None
    message: str | None = None


class ServerLogFileInfo(BaseModel):
    filename: str
    size_bytes: int
    created_at: str
    modified_at: str
    is_current: bool


class ServerLogsIndexResponse(BaseModel):
    log_dir: str
    current_log_file: str | None
    files: list[ServerLogFileInfo]


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


@router.get("/ai-config", response_model=AIConfigResponse, summary="Get AI provider config (admin)")
async def get_ai_config(_: AdminUser) -> dict:
    return await _updater("GET", "/ai-config")


@router.post("/ai-config", response_model=AIConfigResponse, summary="Save AI provider config (admin)")
async def set_ai_config(payload: AIConfigPayload, _: AdminUser) -> dict:
    return await _updater("POST", "/ai-config", payload.model_dump())


def _to_iso_utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


@router.get("/server-logs", response_model=ServerLogsIndexResponse, summary="List persistent server run logs (admin)")
async def list_server_logs(_: AdminUser) -> ServerLogsIndexResponse:
    settings = get_settings()
    log_dir = Path(settings.server_logs_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    current_file_env = os.environ.get("CURRENT_SERVER_LOG_FILE")
    current_log_path = Path(current_file_env).resolve() if current_file_env else None
    files: list[ServerLogFileInfo] = []
    for path in sorted(log_dir.glob("server-*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        files.append(
            ServerLogFileInfo(
                filename=path.name,
                size_bytes=stat.st_size,
                created_at=_to_iso_utc(stat.st_ctime),
                modified_at=_to_iso_utc(stat.st_mtime),
                is_current=bool(current_log_path and path.resolve() == current_log_path),
            )
        )

    return ServerLogsIndexResponse(
        log_dir=str(log_dir),
        current_log_file=current_log_path.name if current_log_path else None,
        files=files,
    )


@router.get(
    "/server-logs/{filename}",
    summary="Download a persistent server run log file (admin)",
)
async def download_server_log(filename: str, _: AdminUser) -> FileResponse:
    settings = get_settings()
    log_dir = Path(settings.server_logs_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.endswith(".log"):
        raise HTTPException(status_code=400, detail="Invalid log filename")

    log_path = (log_dir / safe_name).resolve()
    if log_path.parent != log_dir:
        raise HTTPException(status_code=400, detail="Invalid log path")
    if not log_path.exists() or not log_path.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")

    return FileResponse(
        path=str(log_path),
        media_type="text/plain",
        filename=safe_name,
    )
