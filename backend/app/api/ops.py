"""Admin operations: downloads, indexers, subtitles, storage, health, events."""
import asyncio
import re
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.adapters.base import QueueItem, ServiceKind
from app.core.db import get_db
from app.core.errors import UnifierrError
from app.core.security import require_admin
from app.models import Event
from app.services import health
from app.services.common import adapter_for, get_setting, log_event

router = APIRouter(dependencies=[Depends(require_admin)])
HASH_RE = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")


# ---------------- downloads ----------------

@router.get("/downloads")
async def downloads(db: AsyncSession = Depends(get_db)):
    """qBittorrent torrents merged with the Radarr/Sonarr queues (adds the movie/show title)."""
    items: dict[str, QueueItem] = {}
    dl = up = 0
    async with adapter_for(db, ServiceKind.qbittorrent, required=False) as q:
        if q is not None:
            torrents, info = await asyncio.gather(q.torrents(), q.transfer_info())
            items = {t.id: t for t in torrents}
            dl, up = int(info.get("dl_speed") or 0), int(info.get("up_speed") or 0)
    for kind in (ServiceKind.radarr, ServiceKind.sonarr):
        try:
            async with adapter_for(db, kind, required=False) as arr:
                if arr is None:
                    continue
                for qi in await arr.queue():
                    if qi.id in items:
                        t = items[qi.id]
                        items[qi.id] = t.model_copy(update={
                            "media_title": qi.media_title, "media_type": qi.media_type,
                            "error": t.error or qi.error,
                            "state": "importing" if qi.state == "importing" else t.state})
                    else:
                        items[qi.id] = qi  # e.g. waiting to import, or a client Unifierr doesn't manage
        except UnifierrError:
            continue  # queue enrichment is optional; qBittorrent data is still shown
    return {"items": list(items.values()), "dl_speed": dl, "up_speed": up}


def _hash(item_id: str) -> str:
    h = item_id.lower()
    if not HASH_RE.match(h):
        raise UnifierrError("Only qBittorrent downloads can be paused or removed here.",
                            explanation="This item is in the Radarr/Sonarr queue but not in qBittorrent.")
    return h


@router.post("/downloads/{item_id}/pause", status_code=204)
async def pause(item_id: str, db: AsyncSession = Depends(get_db)):
    async with adapter_for(db, ServiceKind.qbittorrent) as q:
        await q.pause([_hash(item_id)])


@router.post("/downloads/{item_id}/resume", status_code=204)
async def resume(item_id: str, db: AsyncSession = Depends(get_db)):
    async with adapter_for(db, ServiceKind.qbittorrent) as q:
        await q.resume([_hash(item_id)])


@router.delete("/downloads/{item_id}", status_code=204)
async def remove(item_id: str, delete_files: bool = False, db: AsyncSession = Depends(get_db)):
    async with adapter_for(db, ServiceKind.qbittorrent) as q:
        await q.delete([_hash(item_id)], delete_files=delete_files)
    await log_event(db, "downloads", f"Removed download {item_id[:8]}… (files deleted: {delete_files}).")


# ---------------- indexers ----------------

class IndexerIn(BaseModel):
    definition_name: str = Field(min_length=1, max_length=128)
    fields: dict[str, Any] | None = None


class IndexerPatch(BaseModel):
    enabled: bool


@router.get("/indexers")
async def indexers(db: AsyncSession = Depends(get_db)):
    async with adapter_for(db, ServiceKind.prowlarr) as p:
        return await p.indexers()


@router.get("/indexers/schemas")
async def indexer_schemas(db: AsyncSession = Depends(get_db)):
    async with adapter_for(db, ServiceKind.prowlarr) as p:
        return await p.indexer_schemas()


@router.post("/indexers", status_code=201)
async def add_indexer(body: IndexerIn, db: AsyncSession = Depends(get_db)):
    async with adapter_for(db, ServiceKind.prowlarr) as p:
        idx = await p.add_indexer(body.definition_name, body.fields)
    await log_event(db, "indexers", f"Added indexer {idx.name}.")
    return idx


@router.patch("/indexers/{indexer_id}")
async def patch_indexer(indexer_id: int, body: IndexerPatch, db: AsyncSession = Depends(get_db)):
    async with adapter_for(db, ServiceKind.prowlarr) as p:
        return await p.set_indexer_enabled(indexer_id, body.enabled)


@router.delete("/indexers/{indexer_id}", status_code=204)
async def delete_indexer(indexer_id: int, db: AsyncSession = Depends(get_db)):
    async with adapter_for(db, ServiceKind.prowlarr) as p:
        await p.delete_indexer(indexer_id)
    await log_event(db, "indexers", f"Removed indexer #{indexer_id}.")


@router.post("/indexers/test")
async def test_indexers(db: AsyncSession = Depends(get_db)):
    async with adapter_for(db, ServiceKind.prowlarr) as p:
        return await p.test_all_indexers()


# ---------------- subtitles ----------------

@router.get("/subtitles/wanted")
async def subtitles_wanted(db: AsyncSession = Depends(get_db)):
    async with adapter_for(db, ServiceKind.bazarr) as b:
        return await b.wanted()


@router.post("/subtitles/search", status_code=202)
async def subtitles_search(db: AsyncSession = Depends(get_db)):
    async with adapter_for(db, ServiceKind.bazarr) as b:
        await b.search_all_missing()
    await log_event(db, "subtitles", "Started a search for all missing subtitles.")
    return {"ok": True}


# ---------------- storage / health / events ----------------

@router.get("/storage")
async def storage(db: AsyncSession = Depends(get_db)):
    root = await get_setting(db, "root")
    report = None
    if root:
        from app.deploy.folders import check_folders

        report = await run_in_threadpool(check_folders, root)
    disks: dict[str, Any] = {}
    for kind in (ServiceKind.radarr, ServiceKind.sonarr):
        try:
            async with adapter_for(db, kind, required=False) as arr:
                if arr is not None:
                    for d in await arr.disk_space():
                        disks.setdefault(d.path, d)
        except UnifierrError:
            continue
    return {"folders": report, "disks": list(disks.values())}


@router.get("/health/overview")
async def health_overview(db: AsyncSession = Depends(get_db)):
    return await health.overview(db)


@router.get("/events")
async def events(limit: int = Query(100, ge=1, le=500), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Event).order_by(Event.id.desc()).limit(limit))).scalars()
    return [{"id": e.id, "ts": e.ts.isoformat(), "level": e.level, "source": e.source, "message": e.message}
            for e in rows]
