"""Read-only checks that estimate whether a media request can complete."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.adapters.base import ServiceKind
from app.services.common import DOWNLOAD_CLIENTS, adapter_for, get_setting


async def request_preflight(db: AsyncSession, media_type: str) -> dict:
    checks: list[dict[str, str]] = []

    def add(name: str, status: str, message: str, fix: str = "") -> None:
        checks.append({"name": name, "status": status, "message": message, "fix": fix})

    def failed(name: str, exc: Exception) -> None:
        add(name, "blocked", getattr(exc, "message", None) or f"Could not check {name}.",
            getattr(exc, "fix", None) or "Open Health and check this app's connection.")

    arr_kind = ServiceKind.radarr if media_type == "movie" else ServiceKind.sonarr
    try:
        async with adapter_for(db, arr_kind, required=False) as arr:
            if arr is None:
                add(arr_kind.value.capitalize(), "blocked", "The media manager is not connected.",
                    "Connect or install it in Settings → Apps.")
            else:
                status = await arr.ping()
                if not status.ok:
                    add(arr_kind.value.capitalize(), "blocked", status.message,
                        status.issues[0].fix if status.issues else "Check the app in Settings → Apps.")
                else:
                    add(arr_kind.value.capitalize(), "ready", "Connected and responding.")
                    folders = [f.get("path") for f in await arr.root_folders() if f.get("path")]
                    if folders:
                        add("Media folder", "ready", "The media manager has a destination folder configured.")
                    else:
                        add("Media folder", "blocked", "The media manager has no destination folder.",
                            "Run Connect Everything in the setup wizard to add the media folder.")
    except Exception as exc:  # noqa: BLE001 - each check should fail independently
        failed(arr_kind.value.capitalize(), exc)

    try:
        async with adapter_for(db, ServiceKind.prowlarr, required=False) as prowlarr:
            if prowlarr is None:
                add("Indexer", "blocked", "Prowlarr is not connected.",
                    "Connect Prowlarr and add an enabled indexer in Settings → Apps.")
            else:
                status = await prowlarr.ping()
                if not status.ok:
                    add("Indexer", "blocked", status.message,
                        status.issues[0].fix if status.issues else "Check Prowlarr in Settings → Apps.")
                else:
                    enabled = [indexer for indexer in await prowlarr.indexers() if indexer.enabled]
                    if enabled:
                        degraded = [indexer for indexer in enabled if indexer.status not in (None, "ok")]
                        if degraded:
                            add("Indexer", "warning",
                                f"Prowlarr has {len(enabled)} enabled indexer(s); {len(degraded)} report a problem.",
                                "Open Indexers and test or review the indexers reporting a problem.")
                        else:
                            add("Indexer", "ready", f"Prowlarr is responding with {len(enabled)} enabled indexer(s).")
                    else:
                        add("Indexer", "blocked", "Prowlarr has no enabled indexers.",
                            "Enable or add an indexer in Prowlarr, then test it.")
    except Exception as exc:  # noqa: BLE001 - each check should fail independently
        failed("Indexer", exc)

    selected_client = await get_setting(db, "download_client")
    client_kinds = [kind for kind in DOWNLOAD_CLIENTS if kind.value == selected_client]
    if not selected_client:
        client_kinds = list(DOWNLOAD_CLIENTS)
    client_found = False
    for kind in client_kinds:
        try:
            async with adapter_for(db, kind, required=False) as client:
                if client is None:
                    continue
                client_found = True
                status = await client.ping()
                add("Download client", "ready" if status.ok else "blocked",
                    f"{client.display_name} is connected and responding." if status.ok else status.message,
                    "" if status.ok else (status.issues[0].fix if status.issues else "Check it in Settings → Apps."))
                break
        except Exception as exc:  # noqa: BLE001 - report app-specific failures
            client_found = True
            failed("Download client", exc)
            break
    if not client_found:
        add(
            "Download client",
            "warning",
            "No download client is connected yet; requests can be saved, but downloads will wait "
            "until one is connected.",
            "Connect qBittorrent for torrents, or choose a Usenet client if you use a Usenet provider.",
        )

    root = await get_setting(db, "root")
    storage_status, storage_message, storage_fix = await run_in_threadpool(_check_storage, root)
    add("Storage", storage_status, storage_message, storage_fix)

    media_server = await get_setting(db, "media_server")
    if media_server not in (ServiceKind.jellyfin.value, ServiceKind.plex.value):
        add(
            "Library visibility",
            "warning",
            "No Jellyfin or Plex server is connected, so library appearance cannot be checked.",
            "Connect Jellyfin or Plex in Settings → Apps.",
        )
    else:
        try:
            async with adapter_for(db, ServiceKind(media_server), required=False) as server:
                if server is None:
                    add("Library visibility", "warning", f"{media_server.capitalize()} is not connected.",
                        "Connect it in Settings → Apps to verify when media appears.")
                else:
                    status = await server.ping()
                    add("Library visibility", "ready" if status.ok else "warning",
                        f"{server.display_name} is responding." if status.ok else status.message,
                        "" if status.ok else "Check the media server in Settings → Apps.")
        except Exception as exc:  # noqa: BLE001 - visibility is useful but not required to submit
            add("Library visibility", "warning", getattr(exc, "message", None) or "Could not check the media server.",
                getattr(exc, "fix", None) or "Check it in Settings → Apps.")

    verdict = "blocked" if any(check["status"] == "blocked" for check in checks) else (
        "warning" if any(check["status"] == "warning" for check in checks) else "ready"
    )
    return {"verdict": verdict, "checks": checks}


def _check_storage(root: str | None) -> tuple[str, str, str]:
    if not root or not Path(root).is_dir():
        return (
            "blocked",
            "The configured media storage folder is missing.",
            "Check the storage path in Settings → Storage.",
        )
    if not os.access(root, os.W_OK):
        return (
            "blocked",
            "Unifierr cannot write to the media storage folder.",
            "Fix the folder permissions in Settings → Storage.",
    )
    try:
        free_bytes = shutil.disk_usage(root).free
    except OSError:
        return "warning", "Free space could not be checked.", "Check storage capacity on your NAS or server."
    if free_bytes < 20 * 1024**3:
        return (
            "warning",
            f"Only {free_bytes // 1024**3} GB is free; a download may need more space.",
            "Free space or choose a larger storage volume.",
        )
    return "ready", f"Storage is writable with {free_bytes // 1024**3} GB free.", ""
