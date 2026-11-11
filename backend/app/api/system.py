"""Settings, backup and restore."""
import io
import os
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

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
from app.services import updater
from app.services.common import MOVIES_PATH, TORRENTS_MOVIES, TV_PATH, get_all_settings, log_event, set_settings

router = APIRouter(dependencies=[Depends(require_admin)])
MAX_RESTORE_BYTES = 200 * 1024 * 1024


class SettingsIn(BaseModel):
    timezone: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_+\-/]+$")
    language: str | None = Field(default=None, min_length=2, max_length=8, pattern=r"^[a-z]{2,3}(-[A-Za-z]{2})?$")
    puid: int | None = Field(default=None, ge=0, le=65535)
    pgid: int | None = Field(default=None, ge=0, le=65535)
    vpn_enabled: bool | None = None
    vpn_provider: str | None = Field(default=None, max_length=64)
    vpn_type: str | None = Field(default=None, pattern=r"^(openvpn|wireguard)$")
    vpn_server_countries: str | None = Field(default=None, max_length=128)
    vpn_username: str | None = None
    vpn_password: str | None = None
    wireguard_private_key: str | None = None
    plex_claim: str | None = None
    download_client: Literal["qbittorrent", "sabnzbd", "nzbget"] | None = None
    trash_profiles: bool | None = None
    cleanup_review_days: Literal[0, 30, 90, 180] | None = None
    # Empty clears it. https only; private addresses are refused when sending (SafeAsyncClient).
    ntfy_url: str | None = Field(default=None, max_length=300, pattern=r"^(https://[^\s/]+/[A-Za-z0-9_-]+)?$")
    trash_profile: str | None = Field(default=None, max_length=128)


@router.get("/settings")
async def get_settings_route(db: AsyncSession = Depends(get_db)):
    s = await get_all_settings(db)
    return {"root": s["root"], "puid": s["puid"], "pgid": s["pgid"], "timezone": s["timezone"],
            "language": s["language"], "media_server": s["media_server"], "setup_complete": s["setup_complete"],
            "vpn_enabled": s.get("vpn_enabled", False), "vpn_provider": s.get("vpn_provider", ""),
            "vpn_type": s.get("vpn_type", "openvpn"),
            "vpn_server_countries": s.get("vpn_server_countries", ""),
            "vpn_has_openvpn_credentials": bool(s.get("vpn_username_enc") and s.get("vpn_password_enc")),
            "vpn_has_wireguard_key": bool(s.get("wireguard_private_key_enc")),
            "plex_claim_saved": bool(s.get("plex_claim_enc")),
            "download_client": s["download_client"],
            "trash_profiles": s.get("trash_profiles", False), "trash_profile": s.get("trash_profile"),
            "cleanup_review_days": s["cleanup_review_days"], "ntfy_url": s["ntfy_url"],
            "movies_path": MOVIES_PATH, "tv_path": TV_PATH, "downloads_path": TORRENTS_MOVIES.rsplit("/", 1)[0],
            "version": __version__}


@router.put("/settings")
async def put_settings(body: SettingsIn, db: AsyncSession = Depends(get_db)):
    values = body.model_dump(exclude_none=True, exclude={
        "vpn_username", "vpn_password", "wireguard_private_key", "plex_claim",
    })
    secret_settings = {
        "vpn_username": "vpn_username_enc",
        "vpn_password": "vpn_password_enc",
        "wireguard_private_key": "wireguard_private_key_enc",
        "plex_claim": "plex_claim_enc",
    }
    for field, setting_key in secret_settings.items():
        if field in body.model_fields_set:
            value = getattr(body, field)
            if value and len(value) > 512:
                raise HTTPException(400, detail="A supplied secret is too long.")
            values[setting_key] = crypto.encrypt(value)

    current = await get_all_settings(db)
    enabled = values.get("vpn_enabled", current.get("vpn_enabled", False))
    provider = values.get("vpn_provider", current.get("vpn_provider", ""))
    vpn_type = values.get("vpn_type", current.get("vpn_type", "openvpn"))
    username_enc = values.get("vpn_username_enc", current.get("vpn_username_enc"))
    password_enc = values.get("vpn_password_enc", current.get("vpn_password_enc"))
    private_key_enc = values.get("wireguard_private_key_enc", current.get("wireguard_private_key_enc"))
    if enabled and not provider:
        raise HTTPException(400, detail="Choose a VPN provider before enabling VPN routing.")
    if enabled and vpn_type == "openvpn" and not (username_enc and password_enc):
        raise HTTPException(400, detail="Enter the VPN username and password before enabling OpenVPN routing.")
    if enabled and vpn_type == "wireguard" and not private_key_enc:
        raise HTTPException(400, detail="Enter the WireGuard private key before enabling VPN routing.")

    await set_settings(db, values)
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


# ---------------- updates ----------------

class UpdateSettingsIn(BaseModel):
    auto_update: bool


@router.get("/system/update")
async def update_status(db: AsyncSession = Depends(get_db)):
    """Cheap: what is running now and what the last check found. Does not contact the registry."""
    return await updater.status(db)


@router.post("/system/update/check")
async def update_check(db: AsyncSession = Depends(get_db)):
    return await updater.status(db, refresh=True)


@router.post("/system/update/apply", status_code=202)
async def update_apply(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await updater.apply(db, user.username)


@router.put("/system/update/settings")
async def update_settings(body: UpdateSettingsIn, user: User = Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    await set_settings(db, {"auto_update": body.auto_update})
    await log_event(db, "update", f"{user.username} turned automatic updates {'on' if body.auto_update else 'off'}.")
    return await updater.status(db)
