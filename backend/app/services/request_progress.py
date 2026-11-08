"""Build live, best-effort progress for requests from the connected media apps."""
from __future__ import annotations

import logging

from app.adapters.base import MediaItem, QueueItem, ServiceKind
from app.models import MediaRequest
from app.services.common import adapter_for, get_setting

log = logging.getLogger("unifierr.request_progress")


def _matches(item: MediaItem, request: MediaRequest) -> bool:
    if item.media_type != request.media_type:
        return False
    if request.external_id is not None and item.external_id == request.external_id:
        return True
    wanted_id = request.tmdb_id if request.media_type == "movie" else request.tvdb_id
    item_id = item.tmdb_id if request.media_type == "movie" else item.tvdb_id
    if wanted_id is not None and item_id is not None:
        return wanted_id == item_id
    return item.title.casefold().strip() == request.title.casefold().strip()


async def progress_for_requests(db, requests: list[MediaRequest]) -> dict[int, tuple[str, str]]:
    """Return current progress labels without changing request or app state."""
    result: dict[int, tuple[str, str]] = {}
    active = [request for request in requests if request.status == "approved"]
    for request in requests:
        if request.status == "pending":
            result[request.id] = ("pending_review", "Waiting for an admin to approve this request.")
        elif request.status == "denied":
            result[request.id] = ("denied", "This request was declined.")
        elif request.status == "failed":
            result[request.id] = ("needs_attention", request.note or "Unifierr could not send this to the media app.")

    if not active:
        return result

    arr_items: dict[str, list[MediaItem]] = {"movie": [], "series": []}
    queues: list[QueueItem] = []
    arr_available: dict[str, bool] = {"movie": False, "series": False}
    for media_type, kind in (("movie", ServiceKind.radarr), ("series", ServiceKind.sonarr)):
        try:
            async with adapter_for(db, kind, required=False) as arr:
                if arr is None:
                    continue
                if media_type == "movie":
                    arr_items[media_type] = await arr.list_movies()
                else:
                    arr_items[media_type] = await arr.list_series()
                queues.extend(await arr.queue())
                arr_available[media_type] = True
        except Exception as exc:  # noqa: BLE001 - best-effort status must not break request listing
            log.warning("Could not read %s request progress: %s", kind.value, exc)

    server_items: list[MediaItem] = []
    server_checked = False
    media_server = await get_setting(db, "media_server")
    if media_server in (ServiceKind.jellyfin.value, ServiceKind.plex.value):
        try:
            async with adapter_for(db, ServiceKind(media_server), required=False) as server:
                if server is not None:
                    server_items = await server.recently_added(100)
                    server_checked = True
        except Exception as exc:  # noqa: BLE001 - library checks are best effort
            log.warning("Could not check the media server for request progress: %s", exc)
            server_items = []

    for request in active:
        if not arr_available[request.media_type]:
            result[request.id] = ("unknown", "Cannot check progress because the media app is unavailable.")
            continue

        managed_item = next((item for item in arr_items[request.media_type] if _matches(item, request)), None)
        matching_queue = next((item for item in queues
                               if item.media_type == request.media_type
                               and item.media_title
                               and item.media_title.casefold().strip() == request.title.casefold().strip()), None)
        if matching_queue and matching_queue.state == "error":
            result[request.id] = ("needs_attention", matching_queue.error or "The download app reported an error.")
            continue
        if matching_queue and matching_queue.state in ("completed", "importing"):
            result[request.id] = ("importing", "The media app is importing the completed download.")
            continue
        if matching_queue and matching_queue.state in ("downloading", "paused", "stalled", "checking"):
            result[request.id] = ("downloading", f"Download status: {matching_queue.state}.")
            continue
        if matching_queue:
            result[request.id] = ("searching", "The media app has queued this request and is looking for a release.")
            continue

        has_file = bool(managed_item and managed_item.has_file and (
            request.media_type == "movie" or (managed_item.percent_complete or 0) >= 100
        ))
        if has_file:
            visible = any(_matches(item, request) for item in server_items)
            if visible:
                result[request.id] = ("available", "This item is visible in the media server library.")
            elif server_checked:
                result[request.id] = (
                    "waiting_for_library",
                    "The file is ready, but Unifierr could not confirm it in recent media-server items.",
                )
            else:
                result[request.id] = ("unknown", "The file is ready, but Unifierr could not check Jellyfin or Plex.")
        elif managed_item:
            result[request.id] = ("searching", "Added to the media app; waiting for a matching release.")
        else:
            result[request.id] = ("searching", "The media app is searching for a matching release.")

    return result
