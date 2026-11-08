"""Unified media search, library view and the request workflow."""
from __future__ import annotations

import asyncio
import logging
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import MediaItem, QueueItem, ServiceKind
from app.core.errors import UnifierrError
from app.models import MediaRequest, User
from app.services.common import MOVIES_PATH, TV_PATH, adapter_for, get_service, get_setting, log_event

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


async def _requests_by_key(db: AsyncSession) -> dict[tuple, MediaRequest]:
    rows = (await db.execute(select(MediaRequest))).scalars()
    return {_key(r.media_type, r.tmdb_id, r.tvdb_id): r for r in rows}


async def _usernames(db: AsyncSession) -> dict[int, str]:
    return {u.id: u.username for u in (await db.execute(select(User))).scalars()}


def request_out(r: MediaRequest, names: dict[int, str], availability: Availability | None = None) -> RequestOut:
    return RequestOut(
        id=r.id, media_type=r.media_type, tmdb_id=r.tmdb_id, tvdb_id=r.tvdb_id, title=r.title, year=r.year,
        poster_url=r.poster_url, status=r.status, availability=availability,
        requested_by=names.get(r.user_id) if r.user_id else None,
        created_at=r.created_at.isoformat(), note=r.note,
    )


async def _annotate(db: AsyncSession, items: list[MediaItem]) -> list[MediaResult]:
    reqs = await _requests_by_key(db)
    names = await _usernames(db)
    downloading = await _queue_titles(db)
    out = []
    for it in items:
        req = reqs.get(_key(it.media_type, it.tmdb_id, it.tvdb_id))
        avail = availability_of(it, downloading, req)
        out.append(MediaResult(**it.model_dump(), availability=avail,
                               request=request_out(req, names, avail) if req else None))
    return out


async def search(db: AsyncSession, q: str, media_type: str) -> list[MediaResult]:
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
    return await _annotate(db, items)


async def library(db: AsyncSession, media_type: str) -> list[MediaResult]:
    kind = ARR_FOR[media_type]
    async with adapter_for(db, kind) as arr:
        items = await (arr.list_movies() if media_type == "movie" else arr.list_series())
    return await _annotate(db, items)


async def recent(db: AsyncSession) -> list[MediaItem]:
    for kind in (ServiceKind.jellyfin, ServiceKind.plex):
        svc = await get_service(db, kind)
        if svc and svc.api_key_enc:
            async with adapter_for(db, kind) as server:
                return await server.recently_added(20)
    return []


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


async def _preferred_profile_id(db: AsyncSession, arr, kind: ServiceKind) -> int | None:
    choice = await get_setting(db, "trash_profile")
    if not choice or not hasattr(arr, "quality_profiles"):
        return None
    from app.services.trash import target_profile_name

    wanted = target_profile_name(kind, str(choice)).strip().lower()
    for p in await arr.quality_profiles():
        if str(p.get("name", "")).strip().lower() == wanted and p.get("id") is not None:
            return int(p["id"])
    return None


async def add_to_arr(db: AsyncSession, req: MediaRequest) -> None:
    """Send an approved request to Radarr/Sonarr (search starts immediately)."""
    kind = ARR_FOR[req.media_type]
    async with adapter_for(db, kind) as arr:
        root = await _root_folder(arr, MOVIES_PATH if req.media_type == "movie" else TV_PATH)
        profile_id = await _preferred_profile_id(db, arr, kind)
        kw = {"quality_profile_id": profile_id} if profile_id is not None else {}
        if req.media_type == "movie":
            if not req.tmdb_id:
                raise UnifierrError("This movie has no TMDB id, so Radarr cannot add it.")
            item = await arr.add_movie(req.tmdb_id, root_folder=root, search=True, **kw)
        else:
            if not req.tvdb_id:
                raise UnifierrError("This show has no TVDB id, so Sonarr cannot add it.")
            item = await arr.add_series(req.tvdb_id, root_folder=root, search=True, **kw)
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
