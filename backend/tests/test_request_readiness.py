from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.adapters.base import HealthStatus, MediaItem, ServiceKind
from app.models import MediaRequest
from app.services import preflight, request_progress


class FakeAdapter:
    def __init__(self, kind: ServiceKind, *, healthy: bool = True):
        self.kind = kind
        self.display_name = kind.value.capitalize()
        self.healthy = healthy

    async def ping(self) -> HealthStatus:
        return HealthStatus(ok=self.healthy, message="Connected" if self.healthy else "Offline")

    async def root_folders(self) -> list[dict[str, str]]:
        return [{"path": "/data/media/movies"}]

    async def indexers(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(enabled=True, status="ok")]

    async def list_movies(self) -> list[MediaItem]:
        return []

    async def list_series(self) -> list[MediaItem]:
        return []

    async def queue(self) -> list:
        return []

    async def recently_added(self, limit: int) -> list[MediaItem]:
        return []


@pytest.mark.asyncio
async def test_preflight_reports_ready_stack_without_mutating_apps(tmp_path, monkeypatch):
    kinds = (
        ServiceKind.radarr,
        ServiceKind.prowlarr,
        ServiceKind.qbittorrent,
        ServiceKind.jellyfin,
    )
    adapters = {kind: FakeAdapter(kind) for kind in kinds}

    @asynccontextmanager
    async def fake_adapter_for(_db, kind, **_kwargs):
        yield adapters.get(kind)

    async def fake_get_setting(_db, key):
        return {
            "download_client": "qbittorrent",
            "media_server": "jellyfin",
            "root": str(tmp_path),
        }.get(key)

    monkeypatch.setattr(preflight, "adapter_for", fake_adapter_for)
    monkeypatch.setattr(preflight, "get_setting", fake_get_setting)
    monkeypatch.setattr(preflight, "_check_storage", lambda _root: ("ready", "Storage is writable.", ""))

    result = await preflight.request_preflight(None, "movie")

    assert result["verdict"] == "ready"
    assert {check["name"] for check in result["checks"]} == {
        "Radarr", "Media folder", "Indexer", "Download client", "Storage", "Library visibility",
    }
    assert all(check["status"] == "ready" for check in result["checks"])


@pytest.mark.asyncio
async def test_progress_confirms_item_in_media_server_library(monkeypatch):
    movie = MediaItem(media_type="movie", title="Dune", tmdb_id=12, external_id=45, has_file=True)
    adapters = {
        ServiceKind.radarr: FakeAdapter(ServiceKind.radarr),
        ServiceKind.jellyfin: FakeAdapter(ServiceKind.jellyfin),
    }
    adapters[ServiceKind.radarr].list_movies = lambda: _async_value([movie])
    adapters[ServiceKind.jellyfin].recently_added = lambda _limit: _async_value([movie])

    @asynccontextmanager
    async def fake_adapter_for(_db, kind, **_kwargs):
        yield adapters.get(kind)

    async def fake_get_setting(_db, key):
        return "jellyfin" if key == "media_server" else None

    monkeypatch.setattr(request_progress, "adapter_for", fake_adapter_for)
    monkeypatch.setattr(request_progress, "get_setting", fake_get_setting)

    request = MediaRequest(
        id=1, status="approved", media_type="movie", title="Dune", tmdb_id=12, external_id=45,
    )
    progress = await request_progress.progress_for_requests(None, [request])

    assert progress[1] == ("available", "This item is visible in the media server library.")


async def _async_value(value):
    return value
