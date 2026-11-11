from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import current_user, require_admin
from app.models import MediaRequest, User
from app.services import media, preflight, request_progress
from app.services.common import log_event

router = APIRouter()


class RequestIn(BaseModel):
    media_type: Literal["movie", "series"]
    tmdb_id: int | None = Field(default=None, gt=0)
    tvdb_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=255)
    year: int | None = Field(default=None, ge=1870, le=2200)
    poster_url: str | None = Field(default=None, max_length=512)


class NoteIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class LibraryDeleteIn(BaseModel):
    confirm: Literal[True]
    delete_files: bool = False


@router.get("/media/search", response_model=list[media.MediaResult])
async def search(q: str = Query(min_length=1, max_length=200),
                 type: Literal["movie", "series", "all"] = "all",  # noqa: A002
                 user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await media.search(db, q, type, user)


@router.get("/media/library", response_model=list[media.MediaResult])
async def library(type: Literal["movie", "series"] = "movie",  # noqa: A002
                  user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await media.library(db, type, user)


@router.delete("/media/library/{media_type}/{external_id}")
async def delete_library_item(
    media_type: Literal["movie", "series"],
    external_id: int = Path(gt=0),
    body: LibraryDeleteIn = Body(...),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    refreshed = await media.delete_library_item(
        db, media_type, external_id, delete_files=body.delete_files
    )
    await log_event(
        db,
        "library",
        f"{admin.username} removed {media_type} entry {external_id} (files deleted: {body.delete_files}).",
    )
    return {"removed": True, "library_refresh_requested": refreshed}


@router.get("/media/recent")
async def recent(_: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await media.recent(db)


@router.get("/media/watch-links")
async def watch_links(_: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await media.watch_links(db)


@router.get("/requests", response_model=list[media.RequestOut])
async def list_requests(status: str | None = Query(default=None, max_length=16),
                        user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(MediaRequest).order_by(MediaRequest.created_at.desc())
    if user.role != "admin":
        stmt = stmt.where(MediaRequest.user_id == user.id)
    if status:
        stmt = stmt.where(MediaRequest.status == status)
    names = await media._usernames(db)
    rows = list((await db.execute(stmt)).scalars())
    progress = await request_progress.progress_for_requests(db, rows)
    return [media.request_out(r, names, stage=progress.get(r.id)) for r in rows]


@router.post("/requests/preflight")
async def request_preflight(body: RequestIn, _: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await preflight.request_preflight(db, body.media_type)


@router.post("/requests", response_model=media.RequestOut, status_code=201)
async def create_request(body: RequestIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    req = await media.create_request(db, user, body.model_dump())
    if user.role != "admin" and req.user_id != user.id:
        raise HTTPException(
            status_code=409,
            detail="This title already has an active request. Check Requests or ask an admin for help.",
        )
    progress = await request_progress.progress_for_requests(db, [req])
    names = await media._usernames(db) if user.role == "admin" else {user.id: user.username}
    return media.request_out(req, names, stage=progress.get(req.id))


async def _get_request(db: AsyncSession, request_id: int) -> MediaRequest:
    req = await db.get(MediaRequest, request_id)
    if req is None:
        raise HTTPException(404, detail="Request not found.")
    return req


@router.post("/requests/{request_id}/approve", response_model=media.RequestOut)
async def approve(request_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    req = await _get_request(db, request_id)
    if req.status not in ("pending", "failed", "denied"):
        raise HTTPException(409, detail="This request was already approved.")
    await media.approve(db, req, admin)
    return media.request_out(req, await media._usernames(db))


@router.post("/requests/{request_id}/deny", response_model=media.RequestOut)
async def deny(request_id: int, body: NoteIn, admin: User = Depends(require_admin),
               db: AsyncSession = Depends(get_db)):
    req = await _get_request(db, request_id)
    if req.status == "approved":
        raise HTTPException(409, detail="This request was already approved and sent to download.")
    req.status, req.note = "denied", body.note
    await db.commit()
    await log_event(db, "requests", f"{admin.username} denied the request for {req.title}.")
    return media.request_out(req, await media._usernames(db))


@router.delete("/requests/{request_id}", status_code=204)
async def delete_request(request_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    req = await _get_request(db, request_id)
    if user.role != "admin" and req.user_id != user.id:
        raise HTTPException(404, detail="Request not found.")
    await db.delete(req)
    await db.commit()
