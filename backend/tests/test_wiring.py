"""Auto-wiring orchestration against recording fakes (test doubles only)."""
import pytest

from app.adapters.base import HealthStatus, ServiceKind
from app.core.db import sessionmaker
from app.services.installer import save_service
from app.services.jobs import Job
from app.services.wiring import run_wiring

CALLS: list[tuple] = []
EXISTING_FOLDERS: dict[str, list[dict]] = {}


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
                return True
            if name in ("authenticate", "create_api_key"):
                return "jf-token"
            if name == "root_folders":
                return EXISTING_FOLDERS.get(self.conn.kind.value, [])
            return {}

        return record


@pytest.fixture
def fakes(monkeypatch):
    CALLS.clear()
    EXISTING_FOLDERS.clear()
    monkeypatch.setattr("app.services.common.make_adapter", lambda conn: Fake(conn))


async def _connect_all(kinds):
    async with sessionmaker()() as db:
        for kind in kinds:
            url = f"http://{kind.value}:1234"
            extra = {"username": "admin", "password": "pw"} if kind == ServiceKind.qbittorrent else {}
            api_key = None if kind == ServiceKind.jellyfin else "key"
            await save_service(db, kind, base_url=url, api_key=api_key, **extra)


async def test_full_wiring_order_and_idempotent_steps(client, fakes):
    await _connect_all([ServiceKind.radarr, ServiceKind.sonarr, ServiceKind.prowlarr, ServiceKind.qbittorrent,
                        ServiceKind.bazarr, ServiceKind.jellyfin])
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
