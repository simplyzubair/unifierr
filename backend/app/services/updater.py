"""Check for a newer Unifierr image and swap the running container for it.

Flow: pull the image Unifierr is running from (same tag, e.g. ghcr.io/<owner>/unifierr:latest) -> compare the
image id -> start a short-lived helper container from the NEW image (app/deploy/selfupdate.py) that recreates
this container with the same settings, waits until it is healthy and rolls back otherwise.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from starlette.concurrency import run_in_threadpool

from app import __version__
from app.core.config import get_settings
from app.core.db import sessionmaker
from app.core.errors import UnifierrError
from app.core.logging import redact
from app.deploy.docker_manager import DockerManager
from app.deploy.selfupdate import RESULT_FILE
from app.services.common import get_setting, log_event
from app.services.installer import docker_manager
from app.services.jobs import jobs

log = logging.getLogger("unifierr.updater")
REVISION_LABEL = "org.opencontainers.image.revision"

# What the last registry check found. Kept in memory; one check per interval is cheap to repeat after a restart.
_checked: dict[str, Any] | None = None
# One update decision at a time: a manual click and the automatic loop must not both start a swap.
_apply_lock = asyncio.Lock()


def _describe(image: Any) -> dict[str, Any]:
    return {
        "id": image.id.removeprefix("sha256:")[:12],
        "revision": (image.labels or {}).get(REVISION_LABEL),
        "created": (image.attrs or {}).get("Created"),
    }


def _describe_running(dm: DockerManager, container: Any) -> tuple[dict[str, Any], str]:
    """What this container runs. Uses the id stored ON the container: after a newer image takes over the tag,
    Docker's containerd image store may no longer have a record for the image that is still running."""
    image_id = container.attrs.get("Image", "")
    try:
        return _describe(dm.client.images.get(image_id)), image_id
    except Exception:  # noqa: BLE001 - record gone; the id alone is enough
        return {"id": image_id.removeprefix("sha256:")[:12], "revision": None, "created": None}, image_id


def _auth() -> dict[str, str] | None:
    s = get_settings()
    return {"username": s.registry_user, "password": s.registry_token} if s.registry_user and s.registry_token else None


def _unsupported(reason: str) -> tuple[dict[str, Any], None]:
    return {"supported": False, "reason": reason}, None


def check_now(dm: DockerManager, *, pull: bool) -> tuple[dict[str, Any], str | None]:
    """Describe this container's image; with `pull`, also fetch the newest one and compare.
    Returns (public info, full id of the newest image or None)."""
    if not dm.available():
        return _unsupported("Docker is not reachable from Unifierr, so it cannot update itself. "
                            "The Docker socket must be mounted (see the install guide).")
    me = dm.self_container()
    if me is None:
        return _unsupported("Unifierr is not running inside a Docker container.")
    container = dm.client.containers.get(me.id)
    ref = (container.attrs.get("Config") or {}).get("Image", "")
    if "@" in ref:
        return _unsupported("This Unifierr is pinned to one fixed image version, so there is nothing newer to pull.")
    if "/" not in ref:
        return _unsupported(f"This Unifierr was built on this computer (image '{ref}'), not downloaded from a "
                            "registry. Switch the compose file to a published image to get updates.")
    current, running_id = _describe_running(dm, container)
    info: dict[str, Any] = {"supported": True, "image": ref, "container": me.name, "current": current}
    if not pull:
        return info, None
    try:
        latest = dm.client.images.pull(ref, auth_config=_auth())
        latest = latest[0] if isinstance(latest, list) else latest
    except Exception as exc:  # noqa: BLE001 - registry/network errors vary widely
        return {**info, "error": f"Could not download the newest image: {redact(str(exc))[:300]}"}, None
    return {**info, "latest": _describe(latest), "available": latest.id != running_id}, latest.id


def read_result() -> dict[str, Any] | None:
    try:
        return json.loads((get_settings().data_dir / RESULT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def start_helper(dm: DockerManager, name: str, target_id: str) -> None:
    """Run the swap in a second container, because this one is about to be stopped.
    Never touches a helper that is still running: removing it mid-swap could leave Unifierr stopped."""
    helper = f"{name}-updater"
    try:
        existing = dm.client.containers.get(helper)
    except Exception:  # noqa: BLE001 - no helper exists, the normal case
        existing = None
    if existing is not None:
        if existing.status in ("created", "running", "restarting"):
            raise UnifierrError("An update is already in progress", status_code=409,
                                explanation="Another update is still being installed.",
                                fix="Wait a minute; Unifierr restarts by itself when it is done.")
        with contextlib.suppress(Exception):
            existing.remove(force=True)  # a finished helper that was not auto-removed
    dm.client.containers.run(
        target_id, name=f"{name}-updater", entrypoint=["python", "-m", "app.deploy.selfupdate"],
        command=[name, target_id], volumes_from=[name], detach=True, auto_remove=True, network_mode="none",
        user="root", labels={"io.unifierr.helper": "true"},
    )


def _remember(info: dict[str, Any]) -> None:
    global _checked
    if info.get("supported") and "available" in info:
        _checked = {"for": info["current"]["id"], "latest": info["latest"], "available": info["available"],
                    "at": datetime.now(UTC).isoformat()}
    elif info.get("error"):
        _checked = {"for": info["current"]["id"], "error": info["error"], "at": datetime.now(UTC).isoformat()}


async def status(db, *, refresh: bool = False) -> dict[str, Any]:
    info, _ = await run_in_threadpool(check_now, docker_manager(), pull=refresh)
    if refresh:
        _remember(info)
    if info.get("supported") and _checked and _checked["for"] == info["current"]["id"]:
        info = {**info, "latest": _checked.get("latest"), "available": _checked.get("available", False),
                "checked_at": _checked["at"], "error": _checked.get("error")}
    settings = get_settings()
    return {
        **info,
        "version": __version__,
        "revision": os.environ.get("UNIFIERR_REVISION") or None,
        "auto_update": bool(await get_setting(db, "auto_update")),
        "check_every_seconds": settings.update_check_seconds,
        "last_result": read_result(),
        "download_url": settings.download_url,
    }


async def apply(db, who: str) -> dict[str, Any]:
    """Check for the newest image and, if there is one, start the swap. The server restarts shortly after."""
    async with _apply_lock:
        info, target = await run_in_threadpool(check_now, docker_manager(), pull=True)
        _remember(info)
        if not info.get("supported"):
            raise UnifierrError("Updates are not available for this installation", explanation=info["reason"],
                                status_code=409)
        if info.get("error"):
            raise UnifierrError("Could not check for updates", explanation=info["error"],
                                fix="Check the server's internet connection and the registry login.",
                                status_code=502)
        if not info["available"] or target is None:
            return {"started": False, "message": "You already have the newest version."}
        await run_in_threadpool(start_helper, docker_manager(), info["container"], target)
        revision = info["latest"]["revision"] or info["latest"]["id"]
        await log_event(db, "update", f"{who} started an update to {revision}.")
        return {"started": True, "message": "Updating. Unifierr restarts in about a minute."}


async def _auto_tick() -> None:
    if _apply_lock.locked():
        return  # a manual update is being decided right now
    async with _apply_lock, sessionmaker()() as db:
        if not await get_setting(db, "auto_update") or jobs.any_running():
            return
        info, target = await run_in_threadpool(check_now, docker_manager(), pull=True)
        _remember(info)
        if not (info.get("supported") and info.get("available") and target):
            return
        previous = read_result()
        if previous and not previous.get("ok") and previous.get("to") == target:
            return  # this exact image already failed (and was rolled back); wait for a newer one
        try:
            await run_in_threadpool(start_helper, docker_manager(), info["container"], target)
        except UnifierrError as exc:  # e.g. a manual update is already running: nothing to do
            log.info("Automatic update skipped: %s", exc.message)
            return
        await log_event(db, "update", "Automatic update started.")


async def auto_update_loop() -> None:
    await asyncio.sleep(60)  # let the server finish starting before the first check
    while True:
        try:
            await _auto_tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Automatic update check failed")
        await asyncio.sleep(max(60, get_settings().update_check_seconds))
