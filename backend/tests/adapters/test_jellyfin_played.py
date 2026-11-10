import httpx

from app.adapters.base import Connection, ServiceKind
from app.adapters.jellyfin import JellyfinAdapter


async def test_played_movie_tmdb_ids_collects_all_users_and_skips_bad_ids(mock):
    mock.get("http://jellyfin:8096/Users").mock(return_value=httpx.Response(200, json=[{"Id": "u1"}, {"Id": "u2"}]))
    mock.get("http://jellyfin:8096/Items").mock(side_effect=[
        httpx.Response(200, json={"Items": [
            {"ProviderIds": {"Tmdb": "123"}}, {"ProviderIds": {"Tmdb": "bad"}}, {"ProviderIds": {}}]}),
        httpx.Response(200, json={"Items": [{"ProviderIds": {"Tmdb": "456"}}]}),
    ])
    adapter = JellyfinAdapter(Connection(ServiceKind.jellyfin, "http://jellyfin:8096", api_key="key"))
    assert await adapter.played_movie_tmdb_ids() == {123, 456}
    await adapter.aclose()
