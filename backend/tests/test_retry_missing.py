"""Missing titles are searched again."""
from app.services import retry_missing


async def test_asks_radarr_and_sonarr_to_search_again(monkeypatch):
    sent = []

    class FakeArr:
        def __init__(self, kind):
            self.kind = kind

        async def _json(self, method, path, json):
            sent.append((self.kind, path, json["name"]))

    class Ctx:
        def __init__(self, kind):
            self.kind = kind

        async def __aenter__(self):
            return FakeArr(self.kind)

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(retry_missing, "adapter_for", lambda db, kind, required: Ctx(kind))
    await retry_missing.search_missing_once()
    assert {(p, n) for _, p, n in sent} == {("/command", "MissingMoviesSearch"), ("/command", "MissingEpisodeSearch")}
