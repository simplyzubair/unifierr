from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.base import MediaItem, ServiceKind
from app.core.db import sessionmaker
from app.services.common import set_settings
from app.services.installer import save_service
from tests.conftest import CSRF, make_admin


class FakeRadarr:
    movies = []
    deleted = None

    def __init__(self, conn):
        pass

    async def aclose(self):
        pass

    async def list_movies(self):
        return self.movies

    async def delete_movie(self, movie_id, delete_files=False):
        FakeRadarr.deleted = (movie_id, delete_files)


class FakeJellyfin:
    watched = set()

    def __init__(self, conn):
        pass

    async def aclose(self):
        pass

    async def played_movie_tmdb_ids(self):
        return self.watched

    async def refresh_library(self):
        pass


@pytest.fixture
def fake_cleanup(monkeypatch):
    FakeRadarr.movies, FakeRadarr.deleted, FakeJellyfin.watched = [], None, set()
    monkeypatch.setattr(
        "app.services.common.make_adapter",
        lambda conn: FakeRadarr(conn) if conn.kind == ServiceKind.radarr else FakeJellyfin(conn),
    )


async def setup_services():
    async with sessionmaker()() as db:
        await save_service(db, ServiceKind.radarr, base_url="http://radarr:7878", api_key="r" * 32)
        await save_service(db, ServiceKind.jellyfin, base_url="http://jellyfin:8096", api_key="j" * 32)


def movie(days=91):
    return MediaItem(
        media_type="movie",
        title="A Movie",
        year=2020,
        tmdb_id=42,
        external_id=7,
        has_file=True,
        file_added_at=(datetime.now(UTC) - timedelta(days=days)).isoformat(),
    )


@pytest.mark.parametrize("days,watched,expected", [(91, False, False), (89, True, False), (91, True, True)])
async def test_due_movie_requires_watched_and_90_days(client, fake_cleanup, days, watched, expected):
    await make_admin(client)
    await setup_services()
    FakeRadarr.movies = [movie(days)]
    FakeJellyfin.watched = {42} if watched else set()
    response = await client.get("/api/media/cleanup")
    assert response.status_code == 200
    assert bool(response.json()) is expected


async def test_snooze_delays_review_until_expired(client, fake_cleanup):
    await make_admin(client)
    await setup_services()
    FakeRadarr.movies = [movie()]
    FakeJellyfin.watched = {42}
    async with sessionmaker()() as db:
        await set_settings(db, {"cleanup_snoozed_until": {"42": (datetime.now(UTC) + timedelta(days=1)).isoformat()}})
    assert (await client.get("/api/media/cleanup")).json() == []
    async with sessionmaker()() as db:
        await set_settings(
            db, {"cleanup_snoozed_until": {"42": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()}}
        )
    assert len((await client.get("/api/media/cleanup")).json()) == 1


async def test_jellyfin_missing_returns_empty(client, fake_cleanup):
    await make_admin(client)
    await setup_services()
    async with sessionmaker()() as db:
        from app.models import Service

        service = await db.get(Service, 2)
        service.enabled = False
        await db.commit()
    assert (await client.get("/api/media/cleanup")).json() == []


async def test_answer_keep_and_delete(client, fake_cleanup):
    await make_admin(client)
    await setup_services()
    FakeRadarr.movies = [movie()]
    keep = await client.post("/api/media/cleanup/7", json={"delete": False}, headers=CSRF)
    assert keep.status_code == 200
    async with sessionmaker()() as db:
        from app.services.common import get_setting

        snooze = await get_setting(db, "cleanup_snoozed_until")
        assert timedelta(days=89) < datetime.fromisoformat(snooze["42"]) - datetime.now(UTC) <= timedelta(days=90)
    deleted = await client.post("/api/media/cleanup/7", json={"delete": True}, headers=CSRF)
    assert deleted.status_code == 200
    assert FakeRadarr.deleted == (7, True)
    async with sessionmaker()() as db:
        from app.services.common import get_setting

        assert "42" not in await get_setting(db, "cleanup_snoozed_until")


async def test_cleanup_routes_require_admin(client):
    await make_admin(client)
    await client.post(
        "/api/users", json={"username": "kid", "password": "kid-password-1", "role": "user"}, headers=CSRF
    )
    await client.post("/api/auth/logout", headers=CSRF)
    await client.post("/api/auth/login", json={"username": "kid", "password": "kid-password-1"}, headers=CSRF)
    assert (await client.get("/api/media/cleanup")).status_code == 403
    assert (await client.post("/api/media/cleanup/7", json={"delete": False}, headers=CSRF)).status_code == 403


@pytest.mark.parametrize("setting,days,expected", [(30, 31, True), (30, 29, False), (0, 400, False)])
async def test_admin_chooses_the_wait_or_never(client, fake_cleanup, setting, days, expected):
    await make_admin(client)
    await setup_services()
    r = await client.put("/api/settings", json={"cleanup_review_days": setting}, headers=CSRF)
    assert r.status_code == 200 and r.json()["cleanup_review_days"] == setting
    FakeRadarr.movies, FakeJellyfin.watched = [movie(days)], {42}
    assert bool((await client.get("/api/media/cleanup")).json()) is expected


async def test_wait_must_be_one_of_the_offered_choices(client):
    await make_admin(client)
    assert (await client.put("/api/settings", json={"cleanup_review_days": 7}, headers=CSRF)).status_code == 422


@pytest.mark.parametrize("hour", [-1, 24])
async def test_download_hours_must_be_a_real_hour(client, hour):
    await make_admin(client)
    r = await client.put("/api/settings", json={"download_start_hour": hour}, headers=CSRF)
    assert r.status_code == 422
