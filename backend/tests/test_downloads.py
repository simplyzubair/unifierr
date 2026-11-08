"""Pause/remove must work through a connected client and explain clearly when the client is not connected."""
import pytest

from app.adapters.base import ServiceKind
from app.core.db import sessionmaker
from app.services.installer import save_service
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
