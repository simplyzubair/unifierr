"""Pause/remove must work through a connected client and explain clearly when the client is not connected."""
import pytest

from app.adapters.base import ServiceKind
from app.core.db import sessionmaker
from app.services.installer import save_service
from app.services.media import DOWNLOAD_SOURCE_KINDS
from tests.conftest import CSRF, make_admin

HASH = "cd6e42e046b62a33d4b2c509b3d535711d825df7"


class FakeQbit:
    paused: list[list[str]] = []

    def __init__(self, conn):
        self.conn = conn

    async def aclose(self):
        pass

    async def pause(self, ids):
        FakeQbit.paused.append(ids)


@pytest.fixture
def fake_qbit(monkeypatch):
    FakeQbit.paused = []
    monkeypatch.setattr("app.services.common.make_adapter", lambda conn: FakeQbit(conn))


async def test_pause_without_connected_client_explains_how_to_fix(client):
    await make_admin(client)
    r = await client.post(f"/api/downloads/{HASH}/pause", headers=CSRF)
    body = r.json()
    assert r.status_code == 409
    assert body["error"] == "qBittorrent is not connected to Unifierr yet"
    assert "Settings" in body["fix"] and "login" in body["explanation"]


async def test_pause_through_connected_client(client, fake_qbit):
    await make_admin(client)
    async with sessionmaker()() as db:
        await save_service(db, ServiceKind.qbittorrent, base_url="http://qbittorrent:8080",
                           username="u", password="p")
    r = await client.post(f"/api/downloads/{HASH}/pause", headers=CSRF)
    assert r.status_code == 204 and FakeQbit.paused == [[HASH]]


@pytest.mark.parametrize("kind", DOWNLOAD_SOURCE_KINDS)
def test_every_download_client_has_what_the_downloads_view_calls(kind):
    """Regression: qBittorrent had torrents() but no queue(), so its torrents silently vanished from Downloads
    (the view hides one client's error so that the others still show)."""
    import inspect

    from app.adapters import ADAPTERS

    for method in ("queue", "transfer_info", "pause", "resume", "retry", "delete"):
        assert inspect.iscoroutinefunction(getattr(ADAPTERS[kind], method, None)), f"{kind}.{method}"


async def test_downloads_view_lists_a_real_qbittorrent_adapter_queue(client):
    """End to end through the real qBittorrent adapter (HTTP mocked), not a hand-written fake."""
    import httpx
    import respx

    await make_admin(client)
    async with sessionmaker()() as db:
        await save_service(db, ServiceKind.qbittorrent, base_url="http://qbittorrent:8080", username="u", password="p")
    torrent = {"hash": HASH, "name": "Some.Movie.2020", "state": "downloading", "progress": 0.5, "size": 100,
               "downloaded": 50, "dlspeed": 1000, "upspeed": 0, "eta": 60, "category": "radarr", "save_path": "/d"}
    with respx.mock(assert_all_called=False) as mock:
        mock.post("http://qbittorrent:8080/api/v2/auth/login").mock(
            return_value=httpx.Response(200, text="Ok.", headers={"set-cookie": "SID=x; Path=/"}))
        mock.get("http://qbittorrent:8080/api/v2/torrents/info").mock(return_value=httpx.Response(200, json=[torrent]))
        mock.get("http://qbittorrent:8080/api/v2/transfer/info").mock(
            return_value=httpx.Response(200, json={"dl_info_speed": 1000, "up_info_speed": 0}))
        data = (await client.get("/api/downloads")).json()
    visible = [(i["source"], i["state"], round(i["progress"])) for i in data["items"]]
    assert visible == [("qbittorrent", "downloading", 50)]
    assert data["dl_speed"] == 1000
