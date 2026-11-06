"""Settings, backup and restore."""
import io
import os
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.core import crypto
from app.core.config import get_settings
from app.core.db import get_db, reset_engine
from app.core.security import require_admin
from app.models import User
from app.services.common import MOVIES_PATH, TORRENTS_MOVIES, TV_PATH, get_all_settings, log_event, set_settings

router = APIRouter(dependencies=[Depends(require_admin)])
MAX_RESTORE_BYTES = 200 * 1024 * 1024


class SettingsIn(BaseModel):
    timezone: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_+\-/]+$")
    language: str | None = Field(default=None, min_length=2, max_length=8, pattern=r"^[a-z]{2,3}(-[A-Za-z]{2})?$")
    puid: int | None = Field(default=None, ge=0, le=65535)
    pgid: int | None = Field(default=None, ge=0, le=65535)


@router.get("/settings")
async def get_settings_route(db: AsyncSession = Depends(get_db)):
    s = await get_all_settings(db)
    return {"root": s["root"], "puid": s["puid"], "pgid": s["pgid"], "timezone": s["timezone"],
            "language": s["language"], "media_server": s["media_server"], "setup_complete": s["setup_complete"],
            "movies_path": MOVIES_PATH, "tv_path": TV_PATH, "downloads_path": TORRENTS_MOVIES.rsplit("/", 1)[0],
            "version": __version__}


@router.put("/settings")
async def put_settings(body: SettingsIn, db: AsyncSession = Depends(get_db)):
    await set_settings(db, body.model_dump(exclude_none=True))
    await log_event(db, "settings", "Settings changed.")
    return await get_settings_route(db)


def _db_path() -> Path:
    url = get_settings().db_url
    if not url.startswith("sqlite"):
        raise HTTPException(400, detail="Built-in backup only supports the default SQLite database.")
    return Path(url.split(":///", 1)[1])


def _make_backup() -> bytes:
    """Consistent copy of the live SQLite database (online backup API) + secret key, zipped."""
    data_dir = get_settings().data_dir
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "unifierr.db"
        _sqlite_copy(_db_path(), snap)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snap, "unifierr.db")
            key = os.environ.get("UNIFIERR_SECRET_KEY")
            if key:
                z.writestr("secret.key", key)
            elif (data_dir / "secret.key").exists():
                z.write(data_dir / "secret.key", "secret.key")
            z.writestr("VERSION", __version__)
        return buf.getvalue()


@router.get("/system/backup")
async def backup(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    data = await run_in_threadpool(_make_backup)
    await log_event(db, "backup", f"{user.username} downloaded a backup.")
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="unifierr-backup-{stamp}.zip"'})


def _sqlite_copy(src_path: Path, dst_path: Path) -> None:
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _clear_sessions(path: Path) -> None:
    """Sessions inside a backup must not come back to life: everyone signs in again."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("DELETE FROM sessions")
        conn.commit()
    finally:
        conn.close()


def _validate_and_extract(raw: bytes, workdir: Path) -> tuple[Path, bytes | None]:
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise HTTPException(400, detail="This is not a Unifierr backup file (not a zip).") from exc
    names = set(z.namelist())
    if "unifierr.db" not in names:
        raise HTTPException(400, detail="This zip does not contain a Unifierr database.")
    info = z.getinfo("unifierr.db")
    if info.file_size > MAX_RESTORE_BYTES * 5:
        raise HTTPException(400, detail="The database in this backup is unexpectedly large.")
    db_file = workdir / "unifierr.db"  # fixed name: never trust paths from the archive
    db_file.write_bytes(z.read("unifierr.db"))
    with open(db_file, "rb") as f:
        if f.read(16) != b"SQLite format 3\x00":
            raise HTTPException(400, detail="The database in this backup is damaged.")
    conn = sqlite3.connect(db_file)
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise HTTPException(400, detail="The database in this backup is damaged.")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"users", "services", "settings"} <= tables:
            raise HTTPException(400, detail="This database is not from Unifierr.")
    finally:
        conn.close()
    key = None
    if "secret.key" in names:
        key = z.read("secret.key").strip()
        try:
            Fernet(key)
        except ValueError as exc:
            raise HTTPException(400, detail="The secret key in this backup is invalid.") from exc
    return db_file, key


@router.post("/system/restore")
async def restore(file: UploadFile, user: User = Depends(require_admin)):
    raw = await file.read(MAX_RESTORE_BYTES + 1)
    if len(raw) > MAX_RESTORE_BYTES:
        raise HTTPException(413, detail="Backup file is too large.")
    data_dir = get_settings().data_dir
    with tempfile.TemporaryDirectory(dir=data_dir) as tmp:
        db_file, key = await run_in_threadpool(_validate_and_extract, raw, Path(tmp))
        if key and os.environ.get("UNIFIERR_SECRET_KEY") and key.decode() != os.environ["UNIFIERR_SECRET_KEY"]:
            raise HTTPException(400, detail="This backup uses a different secret key than UNIFIERR_SECRET_KEY.")
        await reset_engine()
        target = _db_path()
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        # Keep the current database next to it, then copy the backup INTO the live database with
        # SQLite's online backup API (safe even while other connections are open).
        await run_in_threadpool(_sqlite_copy, target, target.with_name(f"unifierr.db.before-restore-{stamp}"))
        await run_in_threadpool(_sqlite_copy, db_file, target)
        await run_in_threadpool(_clear_sessions, target)
        if key and not os.environ.get("UNIFIERR_SECRET_KEY"):
            key_path = data_dir / "secret.key"
            if key_path.exists():
                os.replace(key_path, data_dir / f"secret.key.before-restore-{stamp}")
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(key)
            crypto._fernet.cache_clear()
    from app.migrations import upgrade_db

    await run_in_threadpool(upgrade_db)
    return {"ok": True, "message": "Backup restored. Please sign in again."}
