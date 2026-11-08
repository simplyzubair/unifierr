"""Unified media search, library view and the request workflow."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import MediaItem, QueueItem, ServiceKind
from app.core.errors import UnifierrError
from app.models import MediaRequest, User
from app.services.common import MOVIES_PATH, TV_PATH, adapter_for, get_service, log_event

log = logging.getLogger("unifierr.media")

Availability = Literal["available", "downloading", "requested", "missing", "not_added"]
ARR_FOR = {"movie": ServiceKind.radarr, "series": ServiceKind.sonarr}


class RequestOut(BaseModel):
    id: int
    media_type: str
    tmdb_id: int | None
    tvdb_id: int | None
    title: str
    year: int | None
    poster_url: str | None
    status: str
    stage: str = "unknown"
    stage_message: str = "Progress has not been checked yet."
    availability: Availability | None = None
    requested_by: str | None = None
    created_at: str
    note: str | None = None


class MediaResult(MediaItem):
    request: RequestOut | None = None
    availability: Availability = "not_added"


def _key(media_type: str, tmdb_id: int | None, tvdb_id: int | None) -> tuple:
    return (media_type, tmdb_id if media_type == "movie" else tvdb_id)


def availability_of(item: MediaItem, downloading_titles: set[str], req: MediaRequest | None) -> Availability:
    if item.in_library:
        if item.has_file and (item.media_type == "movie" or (item.percent_complete or 0) >= 100):
            return "available"
        if item.title.lower() in downloading_titles:
            return "downloading"
        return "available" if item.has_file else "missing"
    if req is not None and req.status in ("pending", "approved"):
        return "requested"
    return "not_added"


async def _queue_titles(db: AsyncSession) -> set[str]:
    titles: set[str] = set()
    for kind in (ServiceKind.radarr, ServiceKind.sonarr):
        try:
            async with adapter_for(db, kind, required=False) as arr:
                if arr is None:
                    continue
                items: list[QueueItem] = await arr.queue()
                titles |= {i.media_title.lower() for i in items if i.media_title}
        except Exception as exc:  # noqa: BLE001 - search must still work if a queue fails
            log.warning("Queue lookup failed for %s: %s", kind, exc)
    return titles


async def _requests_by_key(db: AsyncSession, user: User) -> dict[tuple, MediaRequest]:
    stmt = select(MediaRequest)
    if user.role != "admin":
        stmt = stmt.where(MediaRequest.user_id == user.id)
    rows = (await db.execute(stmt)).scalars()
    return {_key(r.media_type, r.tmdb_id, r.tvdb_id): r for r in rows}


async def _usernames(db: AsyncSession) -> dict[int, str]:
    return {u.id: u.username for u in (await db.execute(select(User))).scalars()}


def request_out(
    r: MediaRequest,
    names: dict[int, str],
    availability: Availability | None = None,
    stage: tuple[str, str] | None = None,
) -> RequestOut:
    if stage is None:
        defaults = {
            "pending": ("pending_review", "Waiting for an admin to approve this request."),
            "approved": ("searching", "Sent to the media app; waiting for a matching release."),
            "denied": ("denied", "This request was declined."),
            "failed": ("needs_attention", r.note or "Unifierr could not send this to the media app."),
        }
        stage = defaults.get(r.status, ("unknown", "Progress has not been checked yet."))
    return RequestOut(
        id=r.id, media_type=r.media_type, tmdb_id=r.tmdb_id, tvdb_id=r.tvdb_id, title=r.title, year=r.year,
        poster_url=r.poster_url, status=r.status, availability=availability,
        stage=stage[0], stage_message=stage[1],
        requested_by=names.get(r.user_id) if r.user_id else None,
        created_at=r.created_at.isoformat(), note=r.note,
    )


async def _annotate(db: AsyncSession, items: list[MediaItem], user: User) -> list[MediaResult]:
    reqs = await _requests_by_key(db, user)
    names = await _usernames(db)
    downloading = await _queue_titles(db)
    out = []
    for it in items:
        req = reqs.get(_key(it.media_type, it.tmdb_id, it.tvdb_id))
        avail = availability_of(it, downloading, req)
        out.append(MediaResult(**it.model_dump(), availability=avail,
                               request=request_out(req, names, avail) if req else None))
    return out


async def search(db: AsyncSession, q: str, media_type: str, user: User) -> list[MediaResult]:
    q = q.strip()
    if not q:
        return []
    kinds = [k for t, k in ARR_FOR.items() if media_type in (t, "all")]

    async def one(kind: ServiceKind) -> list[MediaItem]:
        async with adapter_for(db, kind, required=media_type != "all") as arr:
            return await arr.lookup(q) if arr else []

    results = await asyncio.gather(*(one(k) for k in kinds), return_exceptions=True)
    items: list[MediaItem] = []
    errors = []
    for r in results:
        if isinstance(r, Exception):
            errors.append(r)
        else:
            items.extend(r[:40])
    if errors and not items:
        raise errors[0]
    return await _annotate(db, items, user)


async def library(db: AsyncSession, media_type: str, user: User) -> list[MediaResult]:
    kind = ARR_FOR[media_type]
    async with adapter_for(db, kind) as arr:
        items = await (arr.list_movies() if media_type == "movie" else arr.list_series())
        return await _annotate(db, items, user)


async def delete_library_item(
    db: AsyncSession,
    media_type: Literal["movie", "series"],
    external_id: int,
    *,
    delete_files: bool,
) -> bool:
    """Remove one managed title and ask any connected media server to rescan."""
    kind = ARR_FOR[media_type]
    matching_item: MediaItem | None = None
    async with adapter_for(db, kind) as arr:
        items = await (arr.list_movies() if media_type == "movie" else arr.list_series())
        matching_item = next((item for item in items if item.external_id == external_id), None)
        if media_type == "movie":
            await arr.delete_movie(external_id, delete_files=delete_files)
        else:
            await arr.delete_series(external_id, delete_files=delete_files)

    # Clear a stale request so the title can be requested again after removal.
    if matching_item is not None:
        identity_column = MediaRequest.tmdb_id if media_type == "movie" else MediaRequest.tvdb_id
        external_identity = matching_item.tmdb_id if media_type == "movie" else matching_item.tvdb_id
        if external_identity is not None:
            await db.execute(delete(MediaRequest).where(
                MediaRequest.media_type == media_type,
                identity_column == external_identity,
            ))
            await db.commit()

    refreshed = False
    for server_kind in (ServiceKind.jellyfin, ServiceKind.plex):
        try:
            async with adapter_for(db, server_kind, required=False) as server:
                if server is None:
                    continue
                await server.refresh_library()
                refreshed = True
        except Exception:  # noqa: BLE001 - removal succeeded; report refresh as best-effort
            log.warning("Could not refresh %s after library removal", server_kind, exc_info=True)
    return refreshed


async def recent(db: AsyncSession) -> list[MediaItem]:
    for kind in (ServiceKind.jellyfin, ServiceKind.plex):
        svc = await get_service(db, kind)
        if svc and svc.api_key_enc:
            async with adapter_for(db, kind) as server:
                return await server.recently_added(20)
    return []


# ---------------- downloads ----------------

# Every download client whose queue appears in the unified Downloads view.
DOWNLOAD_SOURCE_KINDS: tuple[ServiceKind, ...] = (
    ServiceKind.qbittorrent, ServiceKind.sabnzbd, ServiceKind.nzbget,
)
# "<prefix>:<id>" item ids for clients whose native id is not a torrent hash.
CLIENT_BY_PREFIX: dict[str, ServiceKind] = {
    "sabnzbd": ServiceKind.sabnzbd, "nzbget": ServiceKind.nzbget,
}
HASH_RE = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")


def _same_download(client_id: str, arr_id: str) -> bool:
    """Radarr/Sonarr report the client's download id without Unifierr's '<source>:' prefix."""
    def bare(i: str) -> str:
        prefix, _, rest = i.partition(":")
        return rest if prefix in CLIENT_BY_PREFIX else i

    return client_id.lower() == arr_id.lower() or bare(client_id).lower() == bare(arr_id).lower()


async def downloads_snapshot(db: AsyncSession) -> dict:
    """The unified Downloads view: every connected download client's queue merged with the
    Radarr/Sonarr queues (which add the movie/show title and the importing state), plus speeds."""
    items: dict[str, QueueItem] = {}
    dl = up = 0
    for client_kind in DOWNLOAD_SOURCE_KINDS:
        try:
            async with adapter_for(db, client_kind, required=False) as client:
                if client is None:
                    continue
                client_items, info = await asyncio.gather(client.queue(), client.transfer_info())
        except Exception as exc:  # noqa: BLE001 - one broken client must not hide the others
            log.warning("Downloads lookup failed for %s: %s", client_kind, exc)
            continue
        for t in client_items:
            items[t.id] = t
        dl += int(info.get("dl_speed") or 0)
        up += int(info.get("up_speed") or 0)

    for kind in (ServiceKind.radarr, ServiceKind.sonarr):
        try:
            async with adapter_for(db, kind, required=False) as arr:
                if arr is None:
                    continue
                for qi in await arr.queue():
                    match = next((cid for cid in items if _same_download(cid, qi.id)), None)
                    if match is not None:
                        t = items[match]
                        items[match] = t.model_copy(update={
                            "media_title": qi.media_title, "media_type": qi.media_type,
                            "error": t.error or qi.error,
                            "state": "importing" if qi.state == "importing" else t.state})
                    else:
                        items.setdefault(qi.id, qi)  # waiting import, or a client Unifierr does not manage
        except UnifierrError:
            continue  # queue enrichment is optional; the client data is still shown
    item_values = list(items.values())
    item_dl_speed = sum(item.download_speed or 0 for item in item_values)
    item_up_speed = sum(item.upload_speed or 0 for item in item_values)
    return {
        "items": item_values,
        "dl_speed": max(dl, item_dl_speed),
        "up_speed": max(up, item_up_speed),
        "updated_at": datetime.now(UTC).isoformat(),
    }


def _route_item(item_id: str) -> tuple[ServiceKind, str]:
    """Which download client owns this item id, and the id that client understands."""
    lower = item_id.lower()
    if HASH_RE.match(lower):
        return ServiceKind.qbittorrent, lower
    prefix, _, rest = item_id.partition(":")
    if prefix in CLIENT_BY_PREFIX and rest:
        return CLIENT_BY_PREFIX[prefix], rest
    raise UnifierrError(
        "This download cannot be paused, retried or removed here",
        explanation="This item is only in the Radarr/Sonarr queue, not in a download client Unifierr manages.",
    )


async def downloads_action(db: AsyncSession, item_id: str, action: str, *, delete_files: bool = False) -> None:
    """Pause, resume, retry or remove one download in whichever client owns it."""
    kind, raw = _route_item(item_id)
    async with adapter_for(db, kind) as client:
        if action == "pause":
            await client.pause([raw])
        elif action == "resume":
            await client.resume([raw])
        elif action == "retry":
            await client.retry([raw])
        elif action == "delete":
            await client.delete([raw], delete_files=delete_files)
        else:  # pragma: no cover - API routes only pass known actions
            raise UnifierrError(f"Unknown download action: {action}")


# ---------------- requests ----------------

async def _root_folder(arr, preferred: str) -> str:
    """Use Unifierr's standard folder if the app has it, else the app's own existing folder."""
    paths = [f.get("path") for f in await arr.root_folders() if f.get("path")]
    if preferred in paths or not paths:
        if not paths:
            raise UnifierrError(
                f"{arr.display_name} has no media folder yet",
                explanation=f"{arr.display_name} needs to know where to save files before it can add anything.",
                fix="Open Settings → Setup wizard and press \"Connect everything\" once.",
                status_code=409,
            )
        return preferred
    return paths[0]


async def add_to_arr(db: AsyncSession, req: MediaRequest) -> None:
    """Send an approved request to Radarr/Sonarr (search starts immediately)."""
    kind = ARR_FOR[req.media_type]
    async with adapter_for(db, kind) as arr:
        root = await _root_folder(arr, MOVIES_PATH if req.media_type == "movie" else TV_PATH)
        if req.media_type == "movie":
            if not req.tmdb_id:
                raise UnifierrError("This movie has no TMDB id, so Radarr cannot add it.")
            item = await arr.add_movie(req.tmdb_id, root_folder=root, search=True)
        else:
            if not req.tvdb_id:
                raise UnifierrError("This show has no TVDB id, so Sonarr cannot add it.")
            item = await arr.add_series(req.tvdb_id, root_folder=root, search=True)
    req.external_id = item.external_id
    req.status = "approved"


async def create_request(db: AsyncSession, user: User, data: dict) -> MediaRequest:
    media_type = data["media_type"]
    tmdb_id, tvdb_id = data.get("tmdb_id"), data.get("tvdb_id")
    if media_type == "movie" and not tmdb_id or media_type == "series" and not tvdb_id:
        raise UnifierrError("Missing id", explanation="Movies need a tmdb_id and shows need a tvdb_id.")
    if media_type == "movie":
        tvdb_id = None
        match = MediaRequest.tmdb_id == tmdb_id
    else:
        match = MediaRequest.tvdb_id == tvdb_id
    existing = (await db.execute(
        select(MediaRequest).where(MediaRequest.media_type == media_type, match)
    )).scalars().first()
    if existing and existing.status in ("pending", "approved"):
        return existing
    req = existing or MediaRequest(media_type=media_type, tmdb_id=tmdb_id, tvdb_id=tvdb_id)
    req.user_id = user.id
    req.title = data["title"][:255]
    req.year = data.get("year")
    poster = data.get("poster_url")
    req.poster_url = poster if isinstance(poster, str) and poster.startswith("https://") else None
    req.status, req.note = "pending", None
    if existing is None:
        db.add(req)
    await db.commit()
    if user.role == "admin":
        await approve(db, req, user)
    else:
        await log_event(db, "requests", f"{user.username} requested {req.title}.")
    return req


async def approve(db: AsyncSession, req: MediaRequest, admin: User) -> MediaRequest:
    try:
        await add_to_arr(db, req)
        await db.commit()
        await log_event(db, "requests", f"{req.title} was approved by {admin.username} and is being searched.")
    except Exception as exc:
        req.status = "failed"
        req.note = getattr(exc, "message", None) or str(exc)[:500]
        await db.commit()
        await log_event(db, "requests", f"Could not add {req.title}: {req.note}", level="error")
        raise
    return req
