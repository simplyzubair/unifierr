"""Small shared helpers: settings store, event log, connected-service lookup."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import BaseAdapter, Connection, ServiceKind
from app.core.crypto import decrypt
from app.core.errors import UnifierrError
from app.models import Event, Service, Setting

log = logging.getLogger("unifierr")

DEFAULT_SETTINGS: dict[str, Any] = {
    "setup_complete": False,
    "root": None,
    "puid": 1000,
    "pgid": 1000,
    "timezone": "UTC",
    "language": "en",
    "media_server": None,  # jellyfin | plex
    "vpn_enabled": False,
    "vpn_provider": "",
    "vpn_type": "openvpn",
    "vpn_server_countries": "",
    "vpn_container_name": "gluetun",
    "download_client": None,  # qbittorrent | sabnzbd | nzbget (picked in the wizard)
}

# Paths as seen INSIDE the managed containers (all mount <root>/data at /data).
MOVIES_PATH = "/data/media/movies"
TV_PATH = "/data/media/tv"
TORRENTS_MOVIES = "/data/torrents/movies"
TORRENTS_TV = "/data/torrents/tv"
USENET_MOVIES = "/data/usenet/movies"
USENET_TV = "/data/usenet/tv"

# The download client kinds, in the order they are preferred when the user has not chosen one.
DOWNLOAD_CLIENTS: tuple[ServiceKind, ...] = (ServiceKind.qbittorrent, ServiceKind.sabnzbd, ServiceKind.nzbget)


async def get_setting(db: AsyncSession, key: str) -> Any:
    row = await db.get(Setting, key)
    return row.value if row else DEFAULT_SETTINGS.get(key)


async def get_all_settings(db: AsyncSession) -> dict[str, Any]:
    out = dict(DEFAULT_SETTINGS)
    for row in (await db.execute(select(Setting))).scalars():
        out[row.key] = row.value
    return out


async def set_settings(db: AsyncSession, values: dict[str, Any]) -> None:
    for key, value in values.items():
        row = await db.get(Setting, key)
        if row:
            row.value = value
        else:
            db.add(Setting(key=key, value=value))
    await db.commit()


async def log_event(db: AsyncSession, source: str, message: str, level: str = "info",
                    details: dict | None = None) -> None:
    log.log(logging.getLevelName(level.upper()) if level in ("info", "warning", "error") else logging.INFO,
            "[%s] %s", source, message)
    db.add(Event(source=source, message=message, level=level, details=details))
    await db.commit()


async def get_services(
    db: AsyncSession, kind: ServiceKind | str, *, enabled_only: bool = False
) -> list[Service]:
    """Return every instance of a kind in stable default-first (oldest first) order."""
    stmt = select(Service).where(Service.kind == str(kind)).order_by(Service.id)
    if enabled_only:
        stmt = stmt.where(Service.enabled.is_(True))
    return list((await db.execute(stmt)).scalars())


async def get_service(
    db: AsyncSession,
    kind: ServiceKind | str,
    name: str | None = None,
    *,
    service_id: int | None = None,
) -> Service | None:
    """Resolve one instance, or the original/oldest instance when no selector is given."""
    if service_id is not None:
        if name is not None:
            raise ValueError("Select a service by name or id, not both")
        svc = await db.get(Service, service_id)
        return svc if svc is not None and svc.kind == str(kind) else None
    stmt = select(Service).where(Service.kind == str(kind)).order_by(Service.id)
    if name is not None:
        stmt = stmt.where(Service.name == name)
    return (await db.execute(stmt)).scalars().first()


def connection_for(svc: Service) -> Connection:
    return Connection(
        kind=ServiceKind(svc.kind),
        base_url=svc.base_url.rstrip("/"),
        api_key=decrypt(svc.api_key_enc),
        username=svc.username,
        password=decrypt(svc.password_enc),
    )


def make_adapter(conn: Connection) -> BaseAdapter:
    from app.adapters import get_adapter  # imported lazily: registry lives in adapters/__init__.py

    return get_adapter(conn)


@asynccontextmanager
async def adapter_for(
    db: AsyncSession,
    kind: ServiceKind | str,
    name: str | None = None,
    *,
    service_id: int | None = None,
    required: bool = True,
):
    """Yield an adapter for one instance, defaulting to the first enabled instance."""
    svc = await get_service(db, kind, name, service_id=service_id)
    if svc is not None and not svc.enabled and name is None and service_id is None:
        # A disabled original instance must not hide a usable additional one.
        svc = next(iter(await get_services(db, kind, enabled_only=True)), svc)
    if svc is None or not svc.enabled:
        if not required:
            yield None
            return
        display = svc.name if svc is not None else name or str(kind).capitalize()
        raise UnifierrError(
            f"{display} is not connected",
            explanation=f"This feature needs {display}, but Unifierr is not connected to it yet.",
            fix="Open Settings → Apps and add or enable it, or run the Setup wizard.",
            status_code=409,
        )
    adapter = make_adapter(connection_for(svc))
    try:
        yield adapter
    finally:
        await adapter.aclose()


def internal_host_port(svc: Service, default_port: int) -> tuple[str, int, bool]:
    """Host/port that OTHER containers use to reach `svc` (falls back to base_url)."""
    from urllib.parse import urlparse

    url = urlparse(svc.internal_url or svc.base_url)
    ssl = url.scheme == "https"
    return url.hostname or "localhost", url.port or (443 if ssl else default_port), ssl
