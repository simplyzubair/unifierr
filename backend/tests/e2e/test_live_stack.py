"""Live end-to-end test against REAL Radarr, Sonarr, Prowlarr and Jellyfin.

Skipped unless UNIFIERR_E2E=1. Start the apps first (any OS, default ports), then:

    UNIFIERR_E2E=1 E2E_RADARR_CONFIG=<radarr data dir> E2E_SONARR_CONFIG=<...> \
    E2E_PROWLARR_CONFIG=<...> E2E_MEDIA_ROOT=<writable folder> pytest tests/e2e -s

The Jellyfin instance must be fresh (startup wizard not done): Unifierr runs the wizard itself.
API keys are read from the apps' own config.xml files, exactly like Unifierr does for adopted apps.
"""
import os
from pathlib import Path

import pytest

from tests.conftest import CSRF, make_admin

pytestmark = pytest.mark.skipif(os.environ.get("UNIFIERR_E2E") != "1", reason="live stack test (UNIFIERR_E2E=1)")
HOST = os.environ.get("E2E_HOST", "127.0.0.1")


@pytest.fixture
def media_paths(monkeypatch, tmp_path):
    """Real apps on a dev machine can't use /data/...; point the wiring at a local folder instead."""
    root = Path(os.environ.get("E2E_MEDIA_ROOT", tmp_path))
    movies, tv = root / "media" / "movies", root / "media" / "tv"
    movies.mkdir(parents=True, exist_ok=True)
    tv.mkdir(parents=True, exist_ok=True)
    for mod in ("app.services.wiring", "app.services.media"):
        monkeypatch.setattr(f"{mod}.MOVIES_PATH", str(movies))
        monkeypatch.setattr(f"{mod}.TV_PATH", str(tv))
    return movies, tv


async def _wait_job(client, job_id):
    import asyncio

    for _ in range(300):
        job = (await client.get(f"/api/jobs/{job_id}")).json()
        if job["status"] != "running":
            return job
        await asyncio.sleep(1)
    raise AssertionError("job did not finish")


async def test_live_stack_end_to_end(client, media_paths):
    from app.deploy.keys import read_arr_api_key

    await make_admin(client)
    keys = {k: read_arr_api_key(os.environ[f"E2E_{k.upper()}_CONFIG"]) for k in ("radarr", "sonarr", "prowlarr")}
    assert all(keys.values()), "could not read API keys from config.xml"

    # 1. Connect existing apps (adoption)
    ports = {"radarr": 7878, "sonarr": 8989, "prowlarr": 9696}
    for kind, port in ports.items():
        r = await client.post("/api/setup/adopt", json={"kind": kind, "base_url": f"http://{HOST}:{port}",
                                                        "api_key": keys[kind]}, headers=CSRF)
        assert r.status_code == 200, r.text
        assert r.json()["status"]["ok"], r.json()
    r = await client.post("/api/setup/adopt", json={"kind": "jellyfin", "base_url": f"http://{HOST}:8096"},
                          headers=CSRF)
    assert r.status_code == 200, r.text

    # 2. Web login for the app's own page (what Unifierr does after installing an app)
    from app.adapters import get_adapter
    from app.adapters.base import Connection, ServiceKind

    radarr = get_adapter(Connection(ServiceKind.radarr, f"http://{HOST}:7878", api_key=keys["radarr"]))
    await radarr.set_ui_login("admin", "e2e-Password-123")
    host_cfg = await radarr._json("GET", "/config/host")
    assert host_cfg["authenticationMethod"] == "forms" and host_cfg["authenticationRequired"] == "enabled"
    await radarr.aclose()

    # 3. Connect everything, twice (must be idempotent)
    for attempt in (1, 2):
        job = await _wait_job(client, (await client.post("/api/setup/wire", headers=CSRF)).json()["job_id"])
        failed = [(s["name"], s["message"], s["explanation"]) for s in job["steps"] if s["status"] == "failed"]
        print(f"\nwiring attempt {attempt}:", [(s["name"], s["status"]) for s in job["steps"]])
        assert not failed, failed

    services = {s["kind"]: s for s in (await client.get("/api/services")).json()}
    assert services["jellyfin"]["has_api_key"] and services["jellyfin"]["has_login"]
    assert all(s["status"]["ok"] for s in services.values()), services

    # 4. Search + request a movie and a show (needs internet for TMDB/TVDB metadata)
    movies = (await client.get("/api/media/search", params={"q": "Big Buck Bunny", "type": "movie"})).json()
    bbb = next(m for m in movies if m["tmdb_id"] == 10378)
    assert bbb["poster_url"] is None or bbb["poster_url"].startswith("https://")
    req = await client.post("/api/requests", json={"media_type": "movie", "tmdb_id": 10378, "title": bbb["title"],
                                                   "year": bbb["year"]}, headers=CSRF)
    assert req.status_code == 201 and req.json()["status"] == "approved", req.text
    shows = (await client.get("/api/media/search", params={"q": "Pioneer One", "type": "series"})).json()
    assert shows, "Sonarr lookup returned nothing"
    show = shows[0]
    req = await client.post("/api/requests", json={"media_type": "series", "tvdb_id": show["tvdb_id"],
                                                   "title": show["title"]}, headers=CSRF)
    assert req.status_code == 201 and req.json()["status"] == "approved", req.text

    library = (await client.get("/api/media/library", params={"type": "movie"})).json()
    assert any(m["tmdb_id"] == 10378 and m["in_library"] for m in library)
    found = (await client.get("/api/media/search", params={"q": "Big Buck Bunny", "type": "movie"})).json()
    assert next(m for m in found if m["tmdb_id"] == 10378)["availability"] in ("missing", "downloading")

    # 5. Indexers, health, storage
    assert (await client.get("/api/indexers")).status_code == 200
    schemas = (await client.get("/api/indexers/schemas")).json()
    assert len(schemas) > 50
    health = (await client.get("/api/health/overview")).json()
    print("\nhealth:", health["overall"], [i["message"] for i in health["issues"]])
    assert {s["kind"] for s in health["services"]} >= {"radarr", "sonarr", "prowlarr", "jellyfin"}
    storage = (await client.get("/api/storage")).json()
    assert storage["disks"]
