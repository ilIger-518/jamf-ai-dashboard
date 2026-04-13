"""Package record synchronisation router.

Copies package metadata (records) from one Jamf Pro server to one or more
target servers using the Classic API, and optionally transfers the actual
package file via the Jamf Pro v1 JDCS2 API (download-url + upload).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import uuid
from copy import deepcopy
from typing import Annotated, Any, Literal
from xml.sax.saxutils import escape as xml_escape

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import ManagePackageSyncUser
from app.models.server import JamfServer
from app.schemas.package_sync import (
    PackageSyncItem,
    PackageSyncItemResult,
    PackageSyncRequest,
    PackageSyncResponse,
    PackageSyncServerResult,
)
from app.services.encryption import decrypt

router = APIRouter(prefix="/package-sync", tags=["package-sync"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers shared with other routers (intentionally local copies to avoid
# tight coupling between routers).
# ---------------------------------------------------------------------------


async def _get_oauth_token(
    client: httpx.AsyncClient, base_url: str, client_id: str, client_secret: str
) -> str:
    resp = await client.post(
        f"{base_url}/api/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OAuth failed for {base_url}: {resp.status_code}",
        )
    return resp.json()["access_token"]


async def _load_server(db: AsyncSession, server_id: uuid.UUID) -> JamfServer:
    result = await db.execute(select(JamfServer).where(JamfServer.id == server_id))
    server = result.scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    return server


def _normalize_list_payload(
    raw: dict[str, Any], root_key: str, item_key: str
) -> list[dict[str, Any]]:
    val = raw.get(root_key) or []
    if isinstance(val, dict):
        items = val.get(item_key) or []
        if isinstance(items, dict):
            return [items]
        return list(items)
    return list(val)


def _extract_category_name(raw_category: object) -> str | None:
    if isinstance(raw_category, dict):
        return raw_category.get("name")
    if isinstance(raw_category, str):
        return raw_category
    return None


def _strip_package_nonportable_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove server-specific identifiers from a package payload before POSTing to target."""
    blocked = {"id", "uuid", "href", "uri"}
    return {k: v for k, v in payload.items() if k not in blocked}


def _dict_to_xml(root_name: str, value: object) -> str:
    def _node(name: str, v: object) -> str:
        if isinstance(v, dict):
            inner = "".join(_node(k, x) for k, x in v.items())
            return f"<{name}>{inner}</{name}>"
        if isinstance(v, list):
            singular = name[:-1] if name.endswith("s") and len(name) > 1 else "item"
            inner = "".join(_node(singular, x) for x in v)
            return f"<{name}>{inner}</{name}>"
        if v is None:
            return f"<{name}></{name}>"
        if isinstance(v, bool):
            text = "true" if v else "false"
        else:
            text = str(v)
        return f"<{name}>{xml_escape(text)}</{name}>"

    return '<?xml version="1.0" encoding="UTF-8"?>' + _node(root_name, value)


async def _fetch_package_detail(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    package_id: int,
) -> dict[str, Any]:
    resp = await client.get(
        f"{base_url}/JSSResource/packages/id/{package_id}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed to fetch package {package_id}: HTTP {resp.status_code} {resp.text[:300]}"
        )
    data: dict[str, Any] = resp.json().get("package") or {}
    return data


async def _list_target_packages_by_name(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
) -> set[str]:
    """Return the set of package names already present on the target server."""
    resp = await client.get(
        f"{base_url}/JSSResource/packages",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to list packages from target: HTTP {resp.status_code}",
        )
    items = _normalize_list_payload(resp.json(), "packages", "package")
    return {str(i["name"]) for i in items if i.get("name")}


async def _create_package_on_target(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    payload: dict[str, Any],
) -> tuple[list[str], int | None]:
    """Create a package record on target.

    Returns ``(logs, new_package_id)``.  *new_package_id* is ``None`` when the
    ID could not be parsed from the response (file transfer will be skipped).
    """
    endpoint = f"{base_url}/JSSResource/packages/id/0"
    logs: list[str] = []
    new_id: int | None = None

    def _parse_id(resp: httpx.Response) -> int | None:
        # 1. JSON body: {"package": {"id": N}}
        try:
            val = resp.json().get("package", {}).get("id")
            if val is not None:
                return int(val)
        except (KeyError, ValueError, TypeError, Exception):  # noqa: BLE001
            pass

        # 2. Location header: …/packages/id/{N}
        location = resp.headers.get("Location", "")
        if location:
            parts = location.rstrip("/").rsplit("/", 1)
            try:
                return int(parts[-1])
            except (ValueError, IndexError):
                pass

        # 3. XML body: <id>N</id> (Classic API XML response)
        m = re.search(r"<id>\s*(\d+)\s*</id>", resp.text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass

        return None

    json_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    # Try JSON first, then fall back to XML (some Jamf tenants return 415 for JSON)
    for candidate in [f"{endpoint}?format=json", endpoint]:
        logs.append(f"POST {candidate} as JSON")
        resp = await client.post(candidate, headers=json_headers, json={"package": payload})
        if resp.status_code in (200, 201):
            logs.append(f"JSON create succeeded: HTTP {resp.status_code}")
            new_id = _parse_id(resp)
            return logs, new_id
        logs.append(f"JSON create failed: HTTP {resp.status_code}")
        if resp.status_code != 415:
            raise RuntimeError(f"Package create failed: HTTP {resp.status_code} {resp.text[:300]}")

    # XML fallback
    xml_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/xml",
    }
    xml_body = _dict_to_xml("package", payload)
    for candidate in [f"{endpoint}?format=json", endpoint]:
        logs.append(f"POST {candidate} as XML")
        resp = await client.post(candidate, headers=xml_headers, content=xml_body)
        if resp.status_code in (200, 201):
            logs.append(f"XML create succeeded: HTTP {resp.status_code}")
            new_id = _parse_id(resp)
            return logs, new_id
        logs.append(f"XML create failed: HTTP {resp.status_code}")
        if resp.status_code != 415:
            break

    raise RuntimeError(
        f"Package create failed after all attempts: HTTP {resp.status_code} {resp.text[:300]}"
    )


async def _get_package_download_url(
    base_url: str,
    token: str,
    package_id: int,
) -> str:
    """Return the JDCS2 pre-signed download URL for a package file.

    Uses a dedicated client because this is a long-running call that sits
    outside the main sync client's timeout budget.
    """
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{base_url}/api/v1/packages/{package_id}/download-url",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed to get download URL for package #{package_id}: "
            f"HTTP {resp.status_code} — server may not support JDCS2 file API"
        )
    data = resp.json()
    url = data.get("downloadUrl") or data.get("download_url")
    if not url:
        raise RuntimeError(f"No download URL in response for package #{package_id}")
    return str(url)


async def _transfer_package_file(
    *,
    source_base_url: str,
    source_token: str,
    source_package_id: int,
    target_base_url: str,
    target_token: str,
    target_package_id: int,
    filename: str,
) -> list[str]:
    """Download the package binary from *source* and upload it to *target*.

    Uses the Jamf Pro v1 JDCS2 endpoints:
      - ``GET  /api/v1/packages/{id}/download-url``  (source)
      - ``POST /api/v1/packages/{id}/upload``         (target)

    The file is streamed to a temporary file on disk to avoid loading large
    packages entirely into memory.
    """
    logs: list[str] = []

    logs.append(f"Fetching JDCS2 download URL for source package #{source_package_id}")
    download_url = await _get_package_download_url(source_base_url, source_token, source_package_id)
    logs.append("Got download URL")

    tmp_path: str | None = None
    try:
        # Stream-download to a temporary file
        logs.append("Downloading package file from source …")
        async with httpx.AsyncClient(timeout=httpx.Timeout(3600)) as dl_client:
            async with dl_client.stream("GET", download_url, follow_redirects=True) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"Failed to download package file: HTTP {resp.status_code}")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pkg") as tmp:
                    tmp_path = tmp.name
                    total = 0
                    async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                        await asyncio.to_thread(tmp.write, chunk)
                        total += len(chunk)
        logs.append(f"Downloaded {total:,} bytes")

        # Upload from temp file to target
        logs.append(f"Uploading package file to target (package #{target_package_id}) …")
        async with httpx.AsyncClient(timeout=httpx.Timeout(3600)) as ul_client:
            with open(tmp_path, "rb") as fh:
                upload_resp = await ul_client.post(
                    f"{target_base_url}/api/v1/packages/{target_package_id}/upload",
                    headers={"Authorization": f"Bearer {target_token}"},
                    files={"file": (filename, fh, "application/octet-stream")},
                )
        if upload_resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Upload failed: HTTP {upload_resp.status_code} {upload_resp.text[:300]}"
            )
        logs.append(f"Package file uploaded successfully: HTTP {upload_resp.status_code}")
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    return logs


async def _copy_packages_to_server(
    client: httpx.AsyncClient,
    *,
    source_base_url: str,
    source_token: str,
    target_server: JamfServer,
    package_ids: list[int],
    skip_existing: bool,
    transfer_file: bool,
) -> PackageSyncServerResult:
    """Copy the selected package records (and optionally files) to a single target server."""
    target_base_url = target_server.url.rstrip("/")
    target_token = await _get_oauth_token(
        client,
        target_base_url,
        decrypt(target_server.client_id),
        decrypt(target_server.client_secret),
    )

    existing_names = await _list_target_packages_by_name(client, target_base_url, target_token)

    results: list[PackageSyncItemResult] = []
    created = skipped = failed = 0

    for package_id in package_ids:
        item_logs: list[str] = [f"Begin copy for package #{package_id}"]
        file_status: Literal["transferred", "skipped", "failed"] | None = None
        file_message: str | None = None

        try:
            detail = await _fetch_package_detail(client, source_base_url, source_token, package_id)
            name = str(detail.get("name") or f"Package {package_id}")
            filename = str(detail.get("filename") or detail.get("file_name") or name)
            item_logs.append(f"Fetched source package: {name}")

            if skip_existing and name in existing_names:
                skipped += 1
                item_logs.append("Skipped: package with same name already exists on target")
                if transfer_file:
                    file_status = "skipped"
                    file_message = "File transfer skipped — record already existed on target"
                results.append(
                    PackageSyncItemResult(
                        package_id=package_id,
                        name=name,
                        status="skipped",
                        message="Already exists on target",
                        logs=item_logs,
                        file_status=file_status,
                        file_message=file_message,
                    )
                )
                continue

            payload = _strip_package_nonportable_fields(deepcopy(detail))

            create_logs, new_target_id = await _create_package_on_target(
                client, target_base_url, target_token, payload
            )
            item_logs.extend(create_logs)
            created += 1
            existing_names.add(name)
            item_logs.append("Package record copied successfully")

            # Optionally transfer the actual package binary via JDCS2
            if transfer_file:
                if new_target_id is None:
                    file_status = "failed"
                    file_message = (
                        "Could not determine new package ID from create response; "
                        "file transfer skipped"
                    )
                    item_logs.append(f"File transfer skipped: {file_message}")
                else:
                    try:
                        ft_logs = await _transfer_package_file(
                            source_base_url=source_base_url,
                            source_token=source_token,
                            source_package_id=package_id,
                            target_base_url=target_base_url,
                            target_token=target_token,
                            target_package_id=new_target_id,
                            filename=filename,
                        )
                        item_logs.extend(ft_logs)
                        file_status = "transferred"
                    except (RuntimeError, httpx.HTTPError, OSError) as ft_exc:
                        file_status = "failed"
                        # Log the full exception (may include URLs/tokens) server-side only.
                        logger.warning(
                            "Package file transfer failed",
                            extra={
                                "package_id": package_id,
                                "target_server_id": str(target_server.id),
                                "error": str(ft_exc),
                            },
                        )
                        # Return a sanitized message to the frontend (no URLs or tokens).
                        raw_msg = str(ft_exc)
                        sanitized = re.sub(r"https?://\S+", "<url redacted>", raw_msg)
                        file_message = sanitized
                        item_logs.append(f"File transfer failed: {sanitized}")

            results.append(
                PackageSyncItemResult(
                    package_id=package_id,
                    name=name,
                    status="created",
                    logs=item_logs,
                    file_status=file_status,
                    file_message=file_message,
                )
            )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            item_logs.append(
                f"Failure copying package #{package_id} to {target_server.name}: {exc}"
            )
            logger.warning(
                "Package sync item failed",
                extra={
                    "package_id": package_id,
                    "target_server_id": str(target_server.id),
                    "error": str(exc),
                },
            )
            results.append(
                PackageSyncItemResult(
                    package_id=package_id,
                    name=f"Package {package_id}",
                    status="failed",
                    message=str(exc),
                    logs=item_logs,
                )
            )

    return PackageSyncServerResult(
        target_server_id=target_server.id,
        target_server_name=target_server.name,
        created=created,
        skipped=skipped,
        failed=failed,
        results=results,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/packages", response_model=list[PackageSyncItem])
async def list_packages(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: ManagePackageSyncUser,
    server_id: uuid.UUID = Query(...),
) -> list[PackageSyncItem]:
    """List package records from the given Jamf Pro server."""
    server = await _load_server(db, server_id)
    base_url = server.url.rstrip("/")

    async with httpx.AsyncClient(timeout=45) as client:
        token = await _get_oauth_token(
            client,
            base_url,
            decrypt(server.client_id),
            decrypt(server.client_secret),
        )

        raw_items: list[dict[str, Any]] = []
        package_endpoints: list[tuple[str, dict[str, Any] | None, str]] = [
            ("/api/v1/packages", {"page": 0, "page-size": 200}, "modern"),
            ("/JSSResource/packages", None, "classic"),
        ]
        for endpoint, params, _label in package_endpoints:
            resp = await client.get(
                f"{base_url}{endpoint}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                params=params,
            )
            if resp.status_code != 200:
                continue
            payload = resp.json()
            if endpoint.startswith("/api/"):
                if isinstance(payload, dict):
                    raw_items = payload.get("results") or payload.get("packages") or []
                elif isinstance(payload, list):
                    raw_items = payload
            else:
                raw_items = _normalize_list_payload(payload, "packages", "package")
            if raw_items:
                break

        if not raw_items:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to list packages from server",
            )

    out = [
        PackageSyncItem(
            id=int(i["id"]),
            name=i.get("name") or f"Package {i['id']}",
            filename=i.get("filename") or i.get("file_name"),
            category=_extract_category_name(i.get("category")),
        )
        for i in raw_items
        if i.get("id")
    ]
    out.sort(key=lambda x: x.name.lower())
    return out


@router.post("/copy", response_model=PackageSyncResponse)
async def copy_packages(
    body: PackageSyncRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: ManagePackageSyncUser,
) -> PackageSyncResponse:
    """Copy package records from the source server to one or more target servers."""
    source = await _load_server(db, body.source_server_id)
    targets = [await _load_server(db, tid) for tid in body.target_server_ids]

    source_base_url = source.url.rstrip("/")

    async with httpx.AsyncClient(timeout=60) as client:
        source_token = await _get_oauth_token(
            client,
            source_base_url,
            decrypt(source.client_id),
            decrypt(source.client_secret),
        )

        server_results: list[PackageSyncServerResult] = []
        for target in targets:
            result = await _copy_packages_to_server(
                client,
                source_base_url=source_base_url,
                source_token=source_token,
                target_server=target,
                package_ids=body.package_ids,
                skip_existing=body.skip_existing,
                transfer_file=body.transfer_file,
            )
            server_results.append(result)
            logger.info(
                "Package sync completed for target",
                extra={
                    "source_server_id": str(body.source_server_id),
                    "target_server_id": str(target.id),
                    "created": result.created,
                    "skipped": result.skipped,
                    "failed": result.failed,
                },
            )

    return PackageSyncResponse(
        source_server_id=body.source_server_id,
        servers=server_results,
    )
