"""Auto-wiring orchestration against recording fakes (test doubles only)."""
import pytest

from app.adapters.base import HealthStatus, Indexer, ServiceKind
from app.core.db import sessionmaker
from app.services.common import get_service
from app.services.installer import save_service
from app.services.jobs import Job
from app.services.wiring import run_wiring

CALLS: list[tuple] = []
EXISTING_FOLDERS: dict[str, list[dict]] = {}
PROWLARR_INDEXERS: list[Indexer] = []


class Fake:
    def __init__(self, conn):
        self.conn = conn

    async def aclose(self):
        pass

    async def ping(self):
        return HealthStatus(ok=True, message="ok")

    def __getattr__(self, name):
        async def record(*args, **kwargs):
            CALLS.append((self.conn.kind.value, name, args, kwargs))
            if name == "startup_needed":
                return self.conn.username != "existing-user"
            if name in ("authenticate", "create_api_key"):
                return "jf-token"
            if name == "ensure_application":
                return {"id": 1 if kwargs.get("kind") == "radarr" else 2}
            if name == "root_folders":
                return EXISTING_FOLDERS.get(self.conn.kind.value, [])
            if name == "indexers":
                return list(PROWLARR_INDEXERS)
            return {}

        return record


@pytest.fixture
def fakes(monkeypatch):
    CALLS.clear()
    EXISTING_FOLDERS.clear()
    PROWLARR_INDEXERS.clear()
    monkeypatch.setattr("app.services.common.make_adapter", lambda conn: Fake(conn))


async def _connect_all(kinds, *, managed_kinds=(), existing_jellyfin=False):
    async with sessionmaker()() as db:
        for kind in kinds:
            url = f"http://{kind.value}:1234"
            extra = {"username": "admin", "password": "pw"} if kind == ServiceKind.qbittorrent else {}
            if kind == ServiceKind.jellyfin and existing_jellyfin:
                extra = {"username": "existing-user", "password": "existing-password"}
            api_key = None if kind == ServiceKind.jellyfin else "key"
            await save_service(db, kind, base_url=url, api_key=api_key, managed=kind in managed_kinds, **extra)


async def test_full_wiring_order_and_idempotent_steps(client, fakes):
    await _connect_all([ServiceKind.radarr, ServiceKind.sonarr, ServiceKind.prowlarr, ServiceKind.qbittorrent,
                        ServiceKind.bazarr, ServiceKind.jellyfin], managed_kinds={ServiceKind.jellyfin})
    job = Job(id="t", kind="wire")
    result = await run_wiring(job)
    assert result["failed"] == [], [(s.name, s.message) for s in job.steps]
    names = [(k, n) for k, n, _, _ in CALLS]
    assert ("radarr", "ensure_root_folder") in names
    assert ("qbittorrent", "ensure_category") in names
    assert ("prowlarr", "ensure_application") in names
    assert ("bazarr", "ensure_arr_connection") in names
    assert ("jellyfin", "run_startup_wizard") in names
    assert names.count(("jellyfin", "ensure_library")) == 2
    # Notifications are added after Jellyfin got its API key.
    notif = [c for c in CALLS if c[1] == "ensure_media_server_notification"]
    assert len(notif) == 2 and notif[0][3]["api_key"] == "jf-token"
    # Radarr gets qBittorrent's internal host + port, never a localhost guess.
    qb = next(c for c in CALLS if c[0] == "radarr" and c[1] == "ensure_qbittorrent_client")
    assert qb[3]["host"] == "qbittorrent" and qb[3]["port"] == 1234 and qb[3]["password"] == "pw"


async def test_wiring_syncs_torrent_only_indexers_to_radarr_and_sonarr(client, fakes):
    """Torrent indexers are synced too; the setup result must not imply Usenet is required."""
    await _connect_all([ServiceKind.radarr, ServiceKind.sonarr, ServiceKind.prowlarr])
    PROWLARR_INDEXERS.append(Indexer(id=1, name="Public torrent source", protocol="torrent", enabled=True))

    job = Job(id="torrent-only", kind="wire")
    result = await run_wiring(job)

    assert result["failed"] == []
    sync_calls = [c for c in CALLS if c[0] == "prowlarr" and c[1] == "sync_application"]
    assert len(sync_calls) == 2
    sync_step = next(s for s in job.steps if s.name == "Sync indexers to Radarr and Sonarr")
    assert sync_step.status == "ok"
    assert "1 enabled indexer(s)" in sync_step.message
    assert "Usenet" not in sync_step.message


async def test_existing_jellyfin_is_linked_without_changing_its_libraries(client, fakes):
    await _connect_all([ServiceKind.radarr, ServiceKind.sonarr, ServiceKind.jellyfin], existing_jellyfin=True)
    job = Job(id="t", kind="wire")
    result = await run_wiring(job)

    assert result["failed"] == [], [(s.name, s.message) for s in job.steps]
    assert not any(kind == "jellyfin" and name == "ensure_library" for kind, name, _, _ in CALLS)
    assert not any(kind == "jellyfin" and name == "run_startup_wizard" for kind, name, _, _ in CALLS)
    assert sum(kind == "radarr" and name == "ensure_media_server_notification" for kind, name, _, _ in CALLS) == 1
    assert sum(kind == "sonarr" and name == "ensure_media_server_notification" for kind, name, _, _ in CALLS) == 1
    async with sessionmaker()() as db:
        jellyfin = await get_service(db, ServiceKind.jellyfin)
        assert jellyfin is not None
        assert jellyfin.api_key_enc is not None
        assert jellyfin.username is None and jellyfin.password_enc is None
    library_step = next(s for s in job.steps if s.name == "Set up Jellyfin libraries")
    assert library_step.status == "skipped"
    assert "left unchanged" in library_step.message


async def test_wiring_skips_missing_apps_with_reasons(client, fakes):
    await _connect_all([ServiceKind.radarr])
    job = Job(id="t", kind="wire")
    result = await run_wiring(job)
    assert result["failed"] == []
    skipped = [s for s in job.steps if s.status == "skipped"]
    assert skipped and all(s.message for s in skipped)


async def test_wiring_keeps_existing_folder_of_adopted_app(client, fakes):
    EXISTING_FOLDERS["radarr"] = [{"id": 1, "path": "/movies"}]
    await _connect_all([ServiceKind.radarr])  # adopted (managed=False)
    job = Job(id="t", kind="wire")
    await run_wiring(job)
    step = next(s for s in job.steps if s.name == "Set Radarr media folder")
    assert step.status == "skipped" and "/movies" in step.message
    assert not any(c[1] == "ensure_root_folder" for c in CALLS)


async def test_wiring_handles_multiple_arr_instances(client, fakes):
    """Two Radarr instances are wired independently with distinct download categories."""
    async with sessionmaker()() as db:
        await save_service(db, ServiceKind.radarr, base_url="http://radarr:1234", api_key="key")
        await save_service(db, ServiceKind.radarr, base_url="http://radarr4k:1234", api_key="key",
                           name="Radarr 4K")
        await save_service(db, ServiceKind.qbittorrent, base_url="http://qbittorrent:1234",
                           api_key=None, username="admin", password="pw")
    job = Job(id="t", kind="wire")
    result = await run_wiring(job)
    assert result["failed"] == [], [(s.name, s.message) for s in job.steps]
    root_calls = [c for c in CALLS if c[1] == "ensure_root_folder"]
    assert len(root_calls) == 2
    qb_calls = [c for c in CALLS if c[1] == "ensure_qbittorrent_client"]
    assert len(qb_calls) == 2
    categories = {c[3]["category"] for c in qb_calls}
    assert len(categories) == 2  # per-instance categories must never collide


async def test_converter_watches_radarrs_own_movie_folder(client, fakes):
    EXISTING_FOLDERS["radarr"] = [{"id": 1, "path": "/data/Movies"}]  # an adopted NAS layout
    await _connect_all([ServiceKind.radarr, ServiceKind.unmanic])
    job = Job(id="t", kind="wire")
    await run_wiring(job)
    step = next(s for s in job.steps if s.name == "Set up automatic movie converter")
    assert step.status == "ok", step.message
    [(folder, (url, token))] = [c[2] for c in CALLS if c[1] == "ensure_converter"]
    assert folder == "/data/Movies" and url.endswith(":8484") and len(token) >= 32


async def test_no_converter_step_without_unmanic(client, fakes):
    await _connect_all([ServiceKind.radarr])
    job = Job(id="t", kind="wire")
    await run_wiring(job)
    assert not any(s.name == "Set up automatic movie converter" for s in job.steps)
