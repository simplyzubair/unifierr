"""The narrow endpoint Unmanic uses to ask whether a movie is being watched."""
import pytest

from app.adapters.base import HealthStatus, ServiceKind
from app.core.db import sessionmaker
from app.services.installer import save_service


class FakeJellyfin:
    def __init__(self, conn):
        self.conn = conn

    async def aclose(self):
        pass

    async def ping(self):
        return HealthStatus(ok=True, message="ok")

    async def playing_file_names(self):
        return {"Film (2020).mkv"}


@pytest.fixture
async def token(client, monkeypatch):
    monkeypatch.setattr("app.services.common.make_adapter", lambda conn: FakeJellyfin(conn))
    from app.api.converter import converter_token

    async with sessionmaker()() as db:
        await save_service(db, ServiceKind.jellyfin, base_url="http://jellyfin:8096", api_key="k")
        return await converter_token(db)


async def test_reports_playing_by_file_name(client, token):
    h = {"X-Unifierr-Token": token}
    assert (await client.get("/api/converter/playing", params={"name": "Film (2020).mkv"}, headers=h)).json() == {
        "playing": True}
    assert (await client.get("/api/converter/playing", params={"name": "Other.mkv"}, headers=h)).json() == {
        "playing": False}


async def test_wrong_or_missing_token_is_refused(client, token):
    r = await client.get("/api/converter/playing", params={"name": "x.mkv"}, headers={"X-Unifierr-Token": "nope"})
    assert r.status_code == 401
    assert (await client.get("/api/converter/playing", params={"name": "x.mkv"})).status_code == 401


async def test_refused_before_any_token_exists(client):
    r = await client.get("/api/converter/playing", params={"name": "x.mkv"}, headers={"X-Unifierr-Token": ""})
    assert r.status_code == 401
