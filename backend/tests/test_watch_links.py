"""Library/Requests cards open the title in Jellyfin."""
from app.adapters.jellyfin import JellyfinAdapter
from app.services import media
from tests.conftest import make_admin


async def test_needs_sign_in(client):
    assert (await client.get("/api/media/watch-links")).status_code == 401


async def test_empty_without_jellyfin(client):
    media._watch_cache = (0.0, {})
    await make_admin(client)
    r = await client.get("/api/media/watch-links")
    assert r.status_code == 200 and r.json() == {}


async def test_maps_movies_by_tmdb_and_series_by_tvdb(monkeypatch):
    adapter = JellyfinAdapter.__new__(JellyfinAdapter)
    adapter.display_name = "Jellyfin"

    class Resp:
        def __init__(self, data):
            self.data = data

    async def fake_api(method, path, **kw):
        if path == "/System/Info/Public":
            return Resp({"Id": "srv1"})
        return Resp({"Items": [
            {"Type": "Movie", "Id": "m1", "ProviderIds": {"Tmdb": "348"}},
            {"Type": "Series", "Id": "s1", "ProviderIds": {"Tvdb": "74852", "Tmdb": "246"}},
            {"Type": "Movie", "Id": "", "ProviderIds": {"Tmdb": "1"}},
        ]})

    monkeypatch.setattr(adapter, "_api", fake_api)
    monkeypatch.setattr("app.adapters.jellyfin.parse_json", lambda resp, name: resp.data)
    server_id, ids = await adapter.watch_ids()
    assert server_id == "srv1"
    assert ids == {"movie:348": "m1", "series:74852": "s1", "series:tmdb:246": "s1"}
