"""Ready-to-watch phone alerts."""
import pytest

from app.core.db import sessionmaker
from app.models import MediaRequest
from app.services import notify
from app.services.common import get_setting, set_settings
from tests.conftest import CSRF, make_admin


@pytest.fixture
def sent(monkeypatch):
    out = {"messages": [], "stages": {}}

    async def fake_send(url, title, message):
        out["messages"].append((url, title, message))

    stages = out["stages"]

    async def fake_progress(db, rows):
        return {r.id: (stages.get(r.id, "downloading"), "") for r in rows}

    monkeypatch.setattr(notify, "send", fake_send)
    monkeypatch.setattr(notify, "progress_for_requests", fake_progress)
    return out


async def _request(db, title="Big Buck Bunny"):
    req = MediaRequest(media_type="movie", tmdb_id=10378, title=title, year=2008, status="approved")
    db.add(req)
    await db.commit()
    return req


async def test_alert_sent_once_when_ready_and_never_before(client, sent):
    async with sessionmaker()() as db:
        await set_settings(db, {"ntfy_url": "https://ntfy.sh/my-movies"})
        req = await _request(db)
    await notify.check_once()
    assert sent["messages"] == []  # still downloading
    sent["stages"][req.id] = "available"
    await notify.check_once()
    await notify.check_once()
    assert sent["messages"] == [
        ("https://ntfy.sh/my-movies", "Ready to watch", "Big Buck Bunny (2008) is in your library now. Enjoy!")]
    async with sessionmaker()() as db:
        assert await get_setting(db, "notified_requests") == [req.id]


async def test_no_alerts_without_an_address(client, sent):
    async with sessionmaker()() as db:
        req = await _request(db)
    sent["stages"][req.id] = "available"
    await notify.check_once()
    assert sent["messages"] == []


@pytest.mark.parametrize("url,ok", [("https://ntfy.sh/my-movies", True), ("", True),
                                    ("http://ntfy.sh/x", False), ("https://ntfy.sh/", False),
                                    ("file:///etc/passwd", False)])
async def test_only_https_topic_addresses_are_accepted(client, url, ok):
    await make_admin(client)
    r = await client.put("/api/settings", json={"ntfy_url": url}, headers=CSRF)
    assert (r.status_code == 200) is ok
