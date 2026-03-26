"""
Auto-updater service for Jamf AI Dashboard.

Polls for new commits (GitHub API or plain git fetch) on a configured branch,
then applies updates by running:
  git pull → docker compose build <services> → docker compose up -d <services>

Falls back to the previous commit automatically if the backend health check
fails within ROLLBACK_TIMEOUT seconds.

Exposes a small HTTP API (port 8089 — internal network only):
  GET  /status   → current state
  POST /check    → trigger an immediate update check
  POST /apply    → trigger an immediate update (if one is available)
"""

import asyncio
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger("updater")

# ── Configuration (from environment) ─────────────────────────────────────────
PROJECT_DIR      = Path(os.environ.get("PROJECT_DIR", "/project"))
GITHUB_REPO      = os.environ.get("GITHUB_REPO", "")          # "owner/repo" or ""
GITHUB_BRANCH    = os.environ.get("GITHUB_BRANCH", "main")
GITHUB_TOKEN     = os.environ.get("GITHUB_TOKEN", "")         # optional — avoids rate-limits
CHECK_INTERVAL   = int(os.environ.get("CHECK_INTERVAL_MINUTES", "60"))
AUTO_UPDATE      = os.environ.get("AUTO_UPDATE_ENABLED", "false").lower() == "true"
HEALTH_URL       = os.environ.get("HEALTH_URL", "http://backend:8000/api/v1/health")
ROLLBACK_TIMEOUT = int(os.environ.get("ROLLBACK_TIMEOUT_SECONDS", "90"))
APP_SERVICES     = os.environ.get("UPDATE_SERVICES", "backend frontend").split()

_cfg: dict[str, str] = {
    "github_repo": GITHUB_REPO,
    "github_branch": GITHUB_BRANCH,
}

# ── In-memory state ───────────────────────────────────────────────────────────
_state: dict = {
    "current_commit":    "",
    "latest_commit":     "",
    "current_version":   None,
    "latest_version":    None,
    "repo_url":          "",
    "branch":            GITHUB_BRANCH,
    "commit_graph":      [],
    "update_available":  False,
    "last_checked":      None,
    "update_in_progress": False,
    "last_update_result": None,   # "success" | "rolled_back" | "failed"
    "last_update_at":    None,
    "log":               [],
}

app = FastAPI(title="Jamf AI Dashboard Updater", docs_url=None, redoc_url=None)


# ── Schemas ───────────────────────────────────────────────────────────────────
class UpdateStatus(BaseModel):
    current_commit:      str
    latest_commit:       str
    current_version:     str | None
    latest_version:      str | None
    repo_url:            str
    branch:              str
    commit_graph:        list[dict[str, Any]]
    update_available:    bool
    last_checked:        str | None
    update_in_progress:  bool
    last_update_result:  str | None
    last_update_at:      str | None
    log:                 list[str]


class UpdaterConfig(BaseModel):
    repo_url: str
    branch: str = "main"
    repo: str | None = None


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
    custom_api_key_masked: str | None
    custom_chat_api_key_set: bool
    custom_chat_api_key_masked: str | None
    custom_scrape_model: str
    custom_scrape_api_key_set: bool
    custom_scrape_api_key_masked: str | None
    local_embedding_model: str
    custom_embedding_model: str
    custom_embedding_api_key_set: bool
    custom_embedding_api_key_masked: str | None
    message: str | None = None


# ── Internal helpers ──────────────────────────────────────────────────────────
def _emit(msg: str) -> None:
    log.info(msg)
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    _state["log"].append(f"[{ts}] {msg}")
    if len(_state["log"]) > 300:
        _state["log"] = _state["log"][-300:]


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    """Run a subprocess; return (returncode, combined stdout+stderr)."""
    workdir = Path(cwd or PROJECT_DIR)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = (result.stdout + result.stderr).strip()

        # Docker-mounted git worktrees are commonly owned by a different UID than the
        # container user. Teach git to trust the project directory and retry once.
        if (
            result.returncode != 0
            and cmd
            and cmd[0] == "git"
            and ("dubious ownership" in output or "safe.directory" in output)
        ):
            subprocess.run(
                ["git", "config", "--global", "--add", "safe.directory", str(workdir)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            retry = subprocess.run(
                cmd,
                cwd=str(workdir),
                capture_output=True,
                text=True,
                timeout=300,
            )
            return retry.returncode, (retry.stdout + retry.stderr).strip()

        return result.returncode, output
    except subprocess.TimeoutExpired:
        return 1, "Command timed out after 300 s"
    except FileNotFoundError as exc:
        return 1, f"Command not found: {exc}"


def _get_current_commit() -> str:
    code, out = _run(["git", "rev-parse", "--short=12", "HEAD"])
    return out if code == 0 else "unknown"


def _get_current_commit_full() -> str:
    code, out = _run(["git", "rev-parse", "HEAD"])
    return out if code == 0 else ""


def _get_current_version() -> str | None:
    code, out = _run(["git", "describe", "--tags", "--exact-match", "HEAD"])
    if code == 0 and out:
        return out
    return None


def _repo_from_url(repo_url: str) -> str:
    """Convert a GitHub URL to owner/repo format, or pass through owner/repo."""
    value = repo_url.strip()
    if not value:
        return ""

    if value.count("/") == 1 and not value.startswith("http"):
        owner, repo = value.split("/", 1)
        return f"{owner.strip()}/{repo.strip()}"

    parsed = urlparse(value)
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        raise ValueError("Only github.com URLs are supported")

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("GitHub URL must include owner and repository")

    owner = parts[0]
    repo = parts[1]
    return f"{owner}/{repo}"


def _repo_to_url(repo: str) -> str:
    return f"https://github.com/{repo}" if repo else ""


def _repo_from_remote() -> str:
    """Infer owner/repo from git origin when updater config is empty."""
    code, out = _run(["git", "remote", "get-url", "origin"])
    if code != 0 or not out:
        return ""

    value = out.strip()
    if value.startswith("git@github.com:"):
        value = value.replace("git@github.com:", "https://github.com/", 1)
    if value.endswith(".git"):
        value = value[:-4]

    try:
        return _repo_from_url(value)
    except ValueError:
        return ""


def _save_env_value(key: str, value: str) -> None:
    """Persist updater config in /project/.env when available."""
    env_path = PROJECT_DIR / ".env"
    if not env_path.exists():
        return

    text = env_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_env_map() -> dict[str, str]:
    env_path = PROJECT_DIR / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _env_value(key: str, default: str = "") -> str:
    env_map = _read_env_map()
    if key in env_map:
        return env_map[key]
    return os.environ.get(key, default)


def _mask_secret(value: str) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _get_ai_config() -> AIConfigResponse:
    provider = (_env_value("AI_PROVIDER", "local") or "local").strip().lower()
    embedding_provider = (_env_value("EMBEDDING_PROVIDER", "local") or "local").strip().lower()
    api_key = _env_value("CUSTOM_AI_API_KEY", "")
    chat_api_key = _env_value("CUSTOM_CHAT_API_KEY", "")
    scrape_api_key = _env_value("CUSTOM_SCRAPE_API_KEY", "")
    embedding_api_key = _env_value("CUSTOM_EMBEDDING_API_KEY", "")
    return AIConfigResponse(
        provider="custom" if provider == "custom" else "local",
        embedding_provider="custom" if embedding_provider == "custom" else "local",
        ollama_base_url=_env_value("OLLAMA_BASE_URL", "http://ollama:11434"),
        ollama_model=_env_value("OLLAMA_MODEL", ""),
        custom_base_url=_env_value("CUSTOM_AI_BASE_URL", "https://api.openai.com/v1"),
        custom_model=_env_value("CUSTOM_AI_MODEL", "gpt-4o-mini"),
        custom_api_key_set=bool(api_key),
        custom_api_key_masked=_mask_secret(api_key),
        custom_chat_api_key_set=bool(chat_api_key or api_key),
        custom_chat_api_key_masked=_mask_secret(chat_api_key or api_key),
        custom_scrape_model=_env_value("CUSTOM_SCRAPE_MODEL", _env_value("CUSTOM_AI_MODEL", "gpt-4o-mini")),
        custom_scrape_api_key_set=bool(scrape_api_key or api_key),
        custom_scrape_api_key_masked=_mask_secret(scrape_api_key or api_key),
        local_embedding_model=_env_value("EMBEDDING_MODEL_NAME", "nomic-embed-text"),
        custom_embedding_model=_env_value("CUSTOM_EMBEDDING_MODEL", "text-embedding-3-small"),
        custom_embedding_api_key_set=bool(embedding_api_key or api_key),
        custom_embedding_api_key_masked=_mask_secret(embedding_api_key or api_key),
    )


def _list_compose_services() -> list[str]:
    code, out = _run(["docker", "compose", "config", "--services"])
    if code != 0 or not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


async def _get_latest_commit() -> str:
    """Return the latest commit SHA (12 chars) for the configured branch."""
    repo = _cfg["github_repo"] or _repo_from_remote()
    branch = _cfg["github_branch"]

    if repo:
        url = f"https://api.github.com/repos/{repo}/commits/{branch}"
        headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    return r.json().get("sha", "")[:12]
                _emit(f"GitHub API returned {r.status_code}")
        except Exception as exc:
            _emit(f"GitHub API error: {exc}")
        return _state["current_commit"]

    # No GitHub repo configured — use plain git fetch
    code, _ = _run(["git", "fetch", "origin", branch])
    if code != 0:
        return _state["current_commit"]
    code2, out = _run(["git", "rev-parse", "--short=12", f"origin/{branch}"])
    return out if code2 == 0 else _state["current_commit"]


async def _github_get_json(url: str) -> Any:
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        return r.json()


async def _get_latest_version(repo: str) -> str | None:
    if not repo:
        return None

    try:
        release = await _github_get_json(f"https://api.github.com/repos/{repo}/releases/latest")
        tag = release.get("tag_name")
        if tag:
            return tag
    except Exception:
        pass

    try:
        tags = await _github_get_json(f"https://api.github.com/repos/{repo}/tags?per_page=1")
        if isinstance(tags, list) and tags:
            name = tags[0].get("name")
            if name:
                return name
    except Exception:
        pass

    return None


async def _build_commit_graph(current_short: str, latest_short: str) -> list[dict[str, Any]]:
    repo = _cfg["github_repo"] or _repo_from_remote()
    branch = _cfg["github_branch"]
    if not repo:
        return []

    current_full = _get_current_commit_full()
    graph: list[dict[str, Any]] = []

    if current_full and current_short and latest_short and current_short != latest_short:
        try:
            compare = await _github_get_json(
                f"https://api.github.com/repos/{repo}/compare/{current_full}...{branch}"
            )
            commits = compare.get("commits", []) if isinstance(compare, dict) else []
            if isinstance(commits, list):
                graph.append(
                    {
                        "sha": current_short,
                        "message": "Current deployment",
                        "author": "local",
                        "date": datetime.now(timezone.utc).isoformat(),
                        "is_current": True,
                        "is_latest": current_short == latest_short,
                        "is_behind_path": False,
                    }
                )
                for item in commits[-24:]:
                    full_sha = item.get("sha", "")
                    short_sha = full_sha[:12] if full_sha else ""
                    commit_obj = item.get("commit", {})
                    graph.append(
                        {
                            "sha": short_sha,
                            "message": commit_obj.get("message", "").split("\n", 1)[0],
                            "author": (commit_obj.get("author") or {}).get("name", "unknown"),
                            "date": (commit_obj.get("author") or {}).get("date"),
                            "is_current": short_sha == current_short,
                            "is_latest": short_sha == latest_short,
                            "is_behind_path": True,
                        }
                    )
                return graph
        except Exception as exc:
            _emit(f"Compare API unavailable; falling back to branch commits ({exc})")

    try:
        commits = await _github_get_json(
            f"https://api.github.com/repos/{repo}/commits?sha={branch}&per_page=24"
        )
        if not isinstance(commits, list):
            return []
        for item in commits:
            full_sha = item.get("sha", "")
            short_sha = full_sha[:12] if full_sha else ""
            commit_obj = item.get("commit", {})
            graph.append(
                {
                    "sha": short_sha,
                    "message": commit_obj.get("message", "").split("\n", 1)[0],
                    "author": (commit_obj.get("author") or {}).get("name", "unknown"),
                    "date": (commit_obj.get("author") or {}).get("date"),
                    "is_current": short_sha == current_short,
                    "is_latest": short_sha == latest_short,
                    "is_behind_path": False,
                }
            )
    except Exception as exc:
        _emit(f"Commit graph fetch failed: {exc}")

    if current_short and not any(node.get("is_current") for node in graph):
        graph.insert(
            0,
            {
                "sha": current_short,
                "message": "Current deployment (not in recent remote history)",
                "author": "local",
                "date": datetime.now(timezone.utc).isoformat(),
                "is_current": True,
                "is_latest": current_short == latest_short,
                "is_behind_path": False,
            },
        )
    return graph


async def _wait_for_health(timeout: int = ROLLBACK_TIMEOUT) -> bool:
    """Return True when the backend health endpoint reports OK within timeout."""
    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient(timeout=5) as client:
        while asyncio.get_event_loop().time() < deadline:
            try:
                r = await client.get(HEALTH_URL)
                if r.status_code == 200 and r.json().get("status") in ("ok", "degraded"):
                    return True
            except Exception:
                pass
            await asyncio.sleep(5)
    return False


# ── Core operations ───────────────────────────────────────────────────────────
async def check_for_updates() -> None:
    repo = _cfg["github_repo"] or _repo_from_remote()
    _state["current_commit"] = _get_current_commit()
    _state["latest_commit"]  = await _get_latest_commit()
    _state["current_version"] = _get_current_version()
    _state["latest_version"] = await _get_latest_version(repo)
    _state["repo_url"] = _repo_to_url(repo)
    _state["branch"] = _cfg["github_branch"]
    _state["commit_graph"] = await _build_commit_graph(
        _state["current_commit"], _state["latest_commit"]
    )
    _state["last_checked"]   = datetime.now(timezone.utc).isoformat()
    _state["update_available"] = bool(
        _state["latest_commit"]
        and _state["current_commit"] != "unknown"
        and _state["latest_commit"] != _state["current_commit"]
    )
    _emit(
        f"Check: current={_state['current_commit']}  "
        f"latest={_state['latest_commit']}  "
        f"available={_state['update_available']}"
    )


async def apply_update() -> None:
    if _state["update_in_progress"]:
        return

    _state["update_in_progress"] = True
    _state["log"] = []
    prev_commit = _state["current_commit"]

    try:
        _emit(f"Starting update {prev_commit} → {_state['latest_commit']}")
        branch = _cfg["github_branch"]

        # 1. git pull
        code, out = _run(["git", "pull", "origin", branch])
        _emit(f"git pull → exit={code}\n{out}")
        if code != 0:
            raise RuntimeError(f"git pull failed: {out}")

        # 2. docker compose build
        code, out = _run(["docker", "compose", "build"] + APP_SERVICES)
        _emit(f"docker compose build → exit={code}\n{out}")
        if code != 0:
            raise RuntimeError(f"Build failed: {out}")

        # 3. docker compose up -d
        code, out = _run(["docker", "compose", "up", "-d"] + APP_SERVICES)
        _emit(f"docker compose up -d → exit={code}\n{out}")
        if code != 0:
            raise RuntimeError(f"docker compose up failed: {out}")

        # 4. health check
        _emit(f"Waiting up to {ROLLBACK_TIMEOUT} s for health check …")
        healthy = await _wait_for_health()
        if not healthy:
            raise RuntimeError("Health check timed out after update")

        _state["current_commit"]    = _get_current_commit()
        _state["update_available"]  = False
        _state["last_update_result"] = "success"
        _state["last_update_at"]    = datetime.now(timezone.utc).isoformat()
        _emit("Update succeeded ✓")

    except RuntimeError as exc:
        _emit(f"Update failed: {exc} — rolling back to {prev_commit}")

        rc, out = _run(["git", "reset", "--hard", prev_commit])
        _emit(f"git reset --hard → exit={rc}\n{out}")

        b_rc, b_out = _run(["docker", "compose", "build"] + APP_SERVICES)
        _emit(f"rollback build → exit={b_rc}\n{b_out}")

        u_rc, u_out = _run(["docker", "compose", "up", "-d"] + APP_SERVICES)
        _emit(f"rollback up → exit={u_rc}\n{u_out}")

        _state["current_commit"]     = prev_commit
        _state["last_update_result"] = "rolled_back"
        _state["last_update_at"]     = datetime.now(timezone.utc).isoformat()
        _emit("Rollback complete")

    finally:
        _state["update_in_progress"] = False


# ── Background polling loop ───────────────────────────────────────────────────
async def _polling_loop() -> None:
    await asyncio.sleep(15)   # startup grace period
    await check_for_updates()
    if AUTO_UPDATE and _state["update_available"]:
        _emit("Auto-update enabled — applying update on startup")
        await apply_update()

    while True:
        await asyncio.sleep(CHECK_INTERVAL * 60)
        await check_for_updates()
        if AUTO_UPDATE and _state["update_available"]:
            _emit("Auto-update: new version detected — applying")
            await apply_update()


# ── FastAPI routes ────────────────────────────────────────────────────────────
@app.get("/status", response_model=UpdateStatus)
async def get_status() -> UpdateStatus:
    return UpdateStatus(**_state)


@app.get("/config", response_model=UpdaterConfig)
async def get_config() -> UpdaterConfig:
    repo = _cfg["github_repo"]
    branch = _cfg["github_branch"]
    return UpdaterConfig(repo_url=_repo_to_url(repo), branch=branch, repo=repo)


@app.post("/config", response_model=UpdaterConfig)
async def update_config(payload: UpdaterConfig) -> UpdaterConfig:
    branch = payload.branch.strip() or "main"
    try:
        repo = _repo_from_url(payload.repo_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    _cfg["github_repo"] = repo
    _cfg["github_branch"] = branch
    _state["repo_url"] = _repo_to_url(repo)
    _state["branch"] = branch

    # Persist to .env when present so container restarts keep settings.
    _save_env_value("GITHUB_REPO", repo)
    _save_env_value("GITHUB_BRANCH", branch)

    _emit(f"Config updated: repo={repo or '(fallback git remote)'} branch={branch}")
    return UpdaterConfig(repo_url=_repo_to_url(repo), branch=branch, repo=repo)


@app.post("/check", response_model=UpdateStatus)
async def trigger_check() -> UpdateStatus:
    await check_for_updates()
    return UpdateStatus(**_state)


@app.post("/apply")
async def trigger_apply() -> dict:
    if not _state["update_available"]:
        return {"ok": False, "message": "No update available"}
    if _state["update_in_progress"]:
        return {"ok": False, "message": "Update already in progress"}
    asyncio.create_task(apply_update())
    return {"ok": True, "message": "Update started — monitor /status for progress"}


@app.get("/ai-config", response_model=AIConfigResponse)
async def get_ai_config() -> AIConfigResponse:
    return _get_ai_config()


@app.post("/ai-config", response_model=AIConfigResponse)
async def update_ai_config(payload: AIConfigPayload) -> AIConfigResponse:
    provider = payload.provider.strip().lower()
    if provider not in {"local", "custom"}:
        raise HTTPException(status_code=400, detail="Provider must be 'local' or 'custom'.")
    embedding_provider = payload.embedding_provider.strip().lower()
    if embedding_provider not in {"local", "custom"}:
        raise HTTPException(status_code=400, detail="Embedding provider must be 'local' or 'custom'.")

    current = _get_ai_config()
    custom_base_url = payload.custom_base_url.strip() or current.custom_base_url
    custom_model = payload.custom_model.strip() or current.custom_model
    custom_api_key = payload.custom_api_key.strip()
    custom_chat_api_key = payload.custom_chat_api_key.strip()
    custom_scrape_model = payload.custom_scrape_model.strip() or current.custom_scrape_model
    custom_scrape_api_key = payload.custom_scrape_api_key.strip()
    local_embedding_model = payload.local_embedding_model.strip() or current.local_embedding_model
    custom_embedding_model = payload.custom_embedding_model.strip() or current.custom_embedding_model
    custom_embedding_api_key = payload.custom_embedding_api_key.strip()

    if provider == "custom" or embedding_provider == "custom":
        if not custom_base_url:
            raise HTTPException(status_code=400, detail="Custom AI base URL is required.")
        if provider == "custom" and not custom_model:
            raise HTTPException(status_code=400, detail="Custom AI model is required.")
        if provider == "custom" and not (custom_chat_api_key or custom_api_key or current.custom_chat_api_key_set):
            raise HTTPException(status_code=400, detail="Custom chat API key is required.")
    if embedding_provider == "custom" and not custom_embedding_model:
        raise HTTPException(status_code=400, detail="Custom embedding model is required.")
    if embedding_provider == "custom" and not (
        custom_embedding_api_key or custom_api_key or current.custom_embedding_api_key_set
    ):
        raise HTTPException(status_code=400, detail="Custom embedding API key is required.")
    if provider == "custom" and not custom_scrape_model:
        raise HTTPException(status_code=400, detail="Custom scrape model is required.")
    if provider == "custom" and not (
        custom_scrape_api_key or custom_api_key or current.custom_scrape_api_key_set
    ):
        raise HTTPException(status_code=400, detail="Custom scrape API key is required.")
    if embedding_provider == "local" and not local_embedding_model:
        raise HTTPException(status_code=400, detail="Local embedding model is required.")

    _save_env_value("AI_PROVIDER", provider)
    _save_env_value("EMBEDDING_PROVIDER", embedding_provider)
    _save_env_value("CUSTOM_AI_BASE_URL", custom_base_url)
    _save_env_value("CUSTOM_AI_MODEL", custom_model)
    _save_env_value("CUSTOM_SCRAPE_MODEL", custom_scrape_model)
    _save_env_value("EMBEDDING_MODEL_NAME", local_embedding_model)
    _save_env_value("CUSTOM_EMBEDDING_MODEL", custom_embedding_model)
    if custom_api_key:
        _save_env_value("CUSTOM_AI_API_KEY", custom_api_key)
    if custom_chat_api_key:
        _save_env_value("CUSTOM_CHAT_API_KEY", custom_chat_api_key)
    if custom_scrape_api_key:
        _save_env_value("CUSTOM_SCRAPE_API_KEY", custom_scrape_api_key)
    if custom_embedding_api_key:
        _save_env_value("CUSTOM_EMBEDDING_API_KEY", custom_embedding_api_key)

    code, out = _run(["docker", "compose", "up", "-d", "backend"])
    if code != 0:
        raise HTTPException(status_code=502, detail=out or "Failed to restart backend with updated AI settings")

    healthy = await _wait_for_health()
    if not healthy:
        raise HTTPException(status_code=502, detail="Backend restart completed but health check timed out.")

    updated = _get_ai_config()
    updated.message = "AI settings saved and backend restarted."
    return updated


@app.get("/docker-logs", response_model=DockerLogsResponse)
async def get_docker_logs(
    service: str | None = Query(default=None),
    tail: int = Query(default=400, ge=50, le=5000),
) -> DockerLogsResponse:
    services = _list_compose_services()
    selected_service = service.strip() if service else None

    if selected_service and services and selected_service not in services:
        raise HTTPException(status_code=400, detail=f"Unknown docker compose service: {selected_service}")

    cmd = ["docker", "compose", "logs", "--no-color", "--tail", str(tail)]
    if selected_service:
        cmd.append(selected_service)

    code, out = _run(cmd)
    if code != 0:
        raise HTTPException(status_code=502, detail=out or "Failed to load docker compose logs")

    return DockerLogsResponse(
        service=selected_service,
        tail=tail,
        services=services,
        logs=out,
    )


@app.on_event("startup")
async def on_startup() -> None:
    _state["current_commit"] = _get_current_commit()
    _state["current_version"] = _get_current_version()
    _state["repo_url"] = _repo_to_url(_cfg["github_repo"] or _repo_from_remote())
    _state["branch"] = _cfg["github_branch"]
    asyncio.create_task(_polling_loop())


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8089, log_level="info")
