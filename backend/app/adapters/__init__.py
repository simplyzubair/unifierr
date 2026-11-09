"""Integration adapters: one module per external app, plus the registry below."""
from __future__ import annotations

import httpx

from app.adapters.base import BaseAdapter, Connection, ServiceKind
from app.adapters.bazarr import BazarrAdapter
from app.adapters.jellyfin import JellyfinAdapter
from app.adapters.nzbget import NzbgetAdapter
from app.adapters.plex import PlexAdapter
from app.adapters.prowlarr import ProwlarrAdapter
from app.adapters.qbittorrent import QbittorrentAdapter
from app.adapters.radarr import RadarrAdapter
from app.adapters.sabnzbd import SabnzbdAdapter
from app.adapters.sonarr import SonarrAdapter
from app.adapters.unmanic import UnmanicAdapter
from app.core.errors import UnifierrError

ADAPTERS: dict[ServiceKind, type[BaseAdapter]] = {
    ServiceKind.radarr: RadarrAdapter,
    ServiceKind.sonarr: SonarrAdapter,
    ServiceKind.prowlarr: ProwlarrAdapter,
    ServiceKind.qbittorrent: QbittorrentAdapter,
    ServiceKind.sabnzbd: SabnzbdAdapter,
    ServiceKind.nzbget: NzbgetAdapter,
    ServiceKind.bazarr: BazarrAdapter,
    ServiceKind.jellyfin: JellyfinAdapter,
    ServiceKind.plex: PlexAdapter,
    ServiceKind.unmanic: UnmanicAdapter,
}


def get_adapter(conn: Connection, client: httpx.AsyncClient | None = None) -> BaseAdapter:
    """Build the adapter for `conn.kind`. Pass `client` to share an HTTP client (e.g. in tests)."""
    try:
        cls = ADAPTERS[ServiceKind(conn.kind)]
    except (KeyError, ValueError) as exc:
        raise UnifierrError(f"Unknown app type: {conn.kind}") from exc
    return cls(conn, client)


__all__ = ["ADAPTERS", "get_adapter", "BaseAdapter", "Connection", "ServiceKind"]
