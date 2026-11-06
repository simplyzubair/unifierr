"""Request workflow and backup/restore, with a fake Radarr adapter (test double only)."""
import io
import zipfile

import pytest

from app.adapters.base import HealthStatus, MediaItem, QueueItem
from tests.conftest import CSRF, make_admin


class FakeRadarr:
    added: list[int] = []
    added_to: list[str] = []
    folders: list[str] = ["/data/media/movies"]
    display_name = "Radarr"

    def __init__(self, conn):
        self.conn = conn

    async def aclose(self):
        pass

    async def ping(self):
        return HealthStatus(ok=True, version="5.0", message="Connected")

    async def health_issues(self):
        return []

    async def lookup(self, term):
        return [MediaItem(media_type="movie", title="Big Buck Bunny", year=2008, tmdb_id=10378,
                          poster_url="https://image.tmdb.org/p.jpg")]

    async def queue(self):
        return [QueueItem(id="abc", name="x", source="radarr", state="downloading", progress=40,
                          media_title="Big Buck Bunny")]

    async def root_folders(self):
        return [{"id": i, "path": p} for i, p in enumerate(FakeRadarr.folders, 1)]

    async def add_movie(self, tmdb_id, *, root_folder=None, quality_profile_id=None, search=True):
        FakeRadarr.added.append(tmdb_id)
        FakeRadarr.added_to.append(root_folder)
        return MediaItem(media_type="movie", title="Big Buck Bunny", tmdb_id=tmdb_id, external_id=7,
                         in_library=True, monitored=True)


@pytest.fixture
def fake_radarr(monkeypatch):
    FakeRadarr.added, FakeRadarr.added_to, FakeRadarr.folders = [], [], ["/data/media/movies"]
    monkeypatch.setattr("app.services.common.make_adapter", lambda conn: FakeRadarr(conn))
    monkeypatch.setattr("app.services.health.make_adapter", lambda conn: FakeRadarr(conn))


async def _connect_radarr():
    from app.adapters.base import ServiceKind
    from app.core.db import sessionmaker
    from app.services.installer import save_service

    async with sessionmaker()() as db:
        await save_service(db, ServiceKind.radarr, base_url="http://radarr:7878", api_key="k" * 32)


async def test_search_and_user_request_needs_approval(client, fake_radarr):
    await make_admin(client)
    await _connect_radarr()
    await client.post("/api/users", json={"username": "kid", "password": "kid-password-1"}, headers=CSRF)

    r = await client.get("/api/media/search", params={"q": "bunny", "type": "movie"})
    assert r.status_code == 200, r.text
    assert r.json()[0]["availability"] == "not_added"

    await client.post("/api/auth/logout", headers=CSRF)
    await client.post("/api/auth/login", json={"username": "kid", "password": "kid-password-1"}, headers=CSRF)
    body = {"media_type": "movie", "tmdb_id": 10378, "title": "Big Buck Bunny", "year": 2008,
            "poster_url": "javascript:alert(1)"}
    req = (await client.post("/api/requests", json=body, headers=CSRF)).json()
    assert req["status"] == "pending" and req["poster_url"] is None  # unsafe URL dropped
    assert FakeRadarr.added == []
    assert (await client.post(f"/api/requests/{req['id']}/approve", headers=CSRF)).status_code == 403

    await client.post("/api/auth/logout", headers=CSRF)
    await client.post("/api/auth/login", json={"username": "admin", "password": "correct-horse-1"}, headers=CSRF)
    approved = await client.post(f"/api/requests/{req['id']}/approve", headers=CSRF)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert FakeRadarr.added == [10378]
    found = (await client.get("/api/media/search", params={"q": "bunny", "type": "movie"})).json()[0]
    assert found["availability"] == "requested"


async def test_admin_request_is_auto_approved_and_deduplicated(client, fake_radarr):
    await make_admin(client)
    await _connect_radarr()
    body = {"media_type": "movie", "tmdb_id": 10378, "title": "Big Buck Bunny"}
    a = (await client.post("/api/requests", json=body, headers=CSRF)).json()
    b = (await client.post("/api/requests", json=body, headers=CSRF)).json()
    assert a["status"] == "approved" and a["id"] == b["id"]
    assert FakeRadarr.added == [10378]


async def test_request_without_radarr_explains_problem(client):
    await make_admin(client)
    r = await client.post("/api/requests", json={"media_type": "movie", "tmdb_id": 1, "title": "X"}, headers=CSRF)
    assert r.status_code == 409
    assert "not connected" in r.json()["error"]
    assert r.json()["fix"]


async def test_api_keys_are_encrypted_at_rest(client, fake_radarr):
    await make_admin(client)
    await _connect_radarr()
    from app.core.config import get_settings

    raw = (get_settings().data_dir / "unifierr.db").read_bytes()
    assert b"k" * 32 not in raw
    services = (await client.get("/api/services")).json()
    assert services[0]["has_api_key"] is True and "api_key" not in services[0]


async def test_backup_and_restore_roundtrip(client, fake_radarr):
    await make_admin(client)
    await _connect_radarr()
    backup = await client.get("/api/system/backup")
    assert backup.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(backup.content)).namelist()
    assert {"unifierr.db", "secret.key"} <= set(names)

    # Change state, then restore: the extra user must disappear.
    await client.post("/api/users", json={"username": "temp", "password": "temp-password-1"}, headers=CSRF)
    r = await client.post("/api/system/restore", files={"file": ("b.zip", backup.content, "application/zip")},
                          headers=CSRF)
    assert r.status_code == 200, r.text
    await client.post("/api/auth/login", json={"username": "admin", "password": "correct-horse-1"}, headers=CSRF)
    users = [u["username"] for u in (await client.get("/api/users")).json()]
    assert users == ["admin"]
    services = (await client.get("/api/services")).json()
    assert services[0]["status"]["ok"] is True  # key still decrypts


async def test_restore_rejects_garbage(client):
    await make_admin(client)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("unifierr.db", b"not a database")
        z.writestr("../../evil.txt", b"x")
    r = await client.post("/api/system/restore", files={"file": ("b.zip", buf.getvalue(), "application/zip")},
                          headers=CSRF)
    assert r.status_code == 400


async def test_request_uses_existing_folder_of_adopted_radarr(client, fake_radarr):
    # Never break an existing setup: an adopted Radarr keeps saving where it already did.
    FakeRadarr.folders = ["/movies"]
    await make_admin(client)
    await _connect_radarr()
    r = await client.post("/api/requests", json={"media_type": "movie", "tmdb_id": 10378, "title": "BBB"},
                          headers=CSRF)
    assert r.status_code == 201 and FakeRadarr.added_to == ["/movies"]


async def test_request_without_any_media_folder_explains(client, fake_radarr):
    FakeRadarr.folders = []
    await make_admin(client)
    await _connect_radarr()
    r = await client.post("/api/requests", json={"media_type": "movie", "tmdb_id": 10378, "title": "BBB"},
                          headers=CSRF)
    assert r.status_code == 409 and "no media folder" in r.json()["error"] and r.json()["fix"]
