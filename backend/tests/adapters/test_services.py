import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.adapters import ADAPTERS, get_adapter
from app.adapters.base import Connection, ServiceKind
from app.adapters.bazarr import BazarrAdapter
from app.adapters.jellyfin import JellyfinAdapter
from app.adapters.plex import PlexAdapter
from app.adapters.qbittorrent import STATE_MAP, QbittorrentAdapter
from app.core.errors import ServiceUnavailable

QB = "http://qbittorrent:8080"
BZ = "http://bazarr:6767"
JF = "http://jellyfin:8096"
PX = "http://plex:32400"


def qbit():
    return QbittorrentAdapter(Connection(ServiceKind.qbittorrent, QB, username="admin", password="secret"))


def form(route) -> dict[str, list[str]]:
    return parse_qs(route.calls.last.request.content.decode())


def login_ok(mock, sid="abc123"):
    return mock.post(f"{QB}/api/v2/auth/login").respond(200, text="Ok.", headers={"set-cookie": f"SID={sid}; path=/"})


# ================================================================ qBittorrent


async def test_qbit_ping_login_headers_and_version(mock):
    login = login_ok(mock)
    mock.get(f"{QB}/api/v2/app/version").respond(200, text="v5.0.2")
    async with qbit() as a:
        s = await a.ping()
    assert s.ok and s.version == "5.0.2"
    req = login.calls.last.request
    assert req.headers["Referer"] == QB and req.headers["Origin"] == QB
    assert form(login) == {"username": ["admin"], "password": ["secret"]}


async def test_qbit_login_failure_message(mock):
    mock.post(f"{QB}/api/v2/auth/login").respond(200, text="Fails.")
    async with qbit() as a:
        s = await a.ping()
    assert not s.ok and s.message == "qBittorrent rejected the username or password"
    assert s.issues[0].fix and "secret" not in repr(s)


async def test_qbit_ip_ban_is_explained(mock):
    mock.post(f"{QB}/api/v2/auth/login").respond(403, text="Your IP address has been banned")
    async with qbit() as a:
        s = await a.ping()
    assert not s.ok and "blocked" in s.message and "bans" in (s.issues[0].explanation or "")


async def test_qbit_sends_sid_cookie_and_relogs_in_once_on_403(mock):
    login = login_ok(mock)
    calls = iter([httpx.Response(403), httpx.Response(200, json=[])])
    info = mock.get(f"{QB}/api/v2/torrents/info").mock(side_effect=lambda r: next(calls))
    async with qbit() as a:
        assert await a.torrents() == []
    assert login.call_count == 2 and info.call_count == 2
    assert info.calls.last.request.headers["Cookie"] == "SID=abc123"


async def test_qbit_pause_prefers_stop_then_falls_back(mock):
    login_ok(mock)
    stop = mock.post(f"{QB}/api/v2/torrents/stop").respond(404)
    pause = mock.post(f"{QB}/api/v2/torrents/pause").respond(200)
    async with qbit() as a:
        await a.pause(["AAA", "bbb"])
        await a.pause(["ccc"])  # remembers that stop does not exist
    assert stop.call_count == 1 and pause.call_count == 2
    assert form(pause) == {"hashes": ["ccc"]}


async def test_qbit_v5_stop_and_start(mock):
    login_ok(mock)
    stop = mock.post(f"{QB}/api/v2/torrents/stop").respond(200)
    start = mock.post(f"{QB}/api/v2/torrents/start").respond(200)
    async with qbit() as a:
        await a.pause(["AAA", "bbb"])
        await a.resume(["AAA"])
    assert form(stop) == {"hashes": ["aaa|bbb"]} and start.called


async def test_qbit_delete_and_category(mock):
    login_ok(mock)
    dele = mock.post(f"{QB}/api/v2/torrents/delete").respond(200)
    create = mock.post(f"{QB}/api/v2/torrents/createCategory").respond(409)
    edit = mock.post(f"{QB}/api/v2/torrents/editCategory").respond(200)
    async with qbit() as a:
        await a.delete(["ABC"], delete_files=True)
        await a.ensure_category("radarr", "/data/torrents/movies")
    assert form(dele) == {"hashes": ["abc"], "deleteFiles": ["true"]}
    assert create.called and form(edit) == {"category": ["radarr"], "savePath": ["/data/torrents/movies"]}


async def test_qbit_ensure_category_created_no_edit(mock):
    login_ok(mock)
    mock.post(f"{QB}/api/v2/torrents/createCategory").respond(200)
    edit = mock.post(f"{QB}/api/v2/torrents/editCategory")
    async with qbit() as a:
        await a.ensure_category("tv-sonarr", "/data/torrents/tv")
    assert not edit.called


async def test_qbit_preferences_and_transfer(mock):
    login_ok(mock)
    prefs = mock.post(f"{QB}/api/v2/app/setPreferences").respond(200)
    mock.get(f"{QB}/api/v2/transfer/info").respond(json={"dl_info_speed": 100, "up_info_speed": 5,
                                                         "connection_status": "connected"})
    async with qbit() as a:
        await a.set_preferences({"save_path": "/data/torrents"})
        info = await a.transfer_info()
    assert json.loads(form(prefs)["json"][0]) == {"save_path": "/data/torrents"}
    assert info["dl_speed"] == 100 and info["up_speed"] == 5


STATE_TABLE = {
    "downloading": "downloading", "forcedDL": "downloading", "metaDL": "downloading", "stalledDL": "stalled",
    "pausedDL": "paused", "stoppedDL": "paused", "uploading": "seeding", "forcedUP": "seeding",
    "stalledUP": "seeding", "pausedUP": "completed", "stoppedUP": "completed", "queuedDL": "queued",
    "queuedUP": "queued", "checkingDL": "checking", "checkingUP": "checking", "checkingResumeData": "checking",
    "error": "error", "missingFiles": "error", "moving": "checking",
}


@pytest.mark.parametrize(("raw", "expected"), STATE_TABLE.items())
def test_qbit_state_table(raw, expected):
    assert STATE_MAP[raw] == expected


async def test_qbit_torrents_mapping(mock):
    login_ok(mock)
    mock.get(f"{QB}/api/v2/torrents/info").respond(json=[
        {"hash": "ABCDEF", "name": "Movie", "state": "downloading", "progress": 0.4237, "size": 1000,
         "downloaded": 424, "dlspeed": 50, "upspeed": 1, "eta": 600, "category": "radarr", "save_path": "/data/t"},
        {"hash": "FF", "name": "Stuck", "state": "missingFiles", "progress": 1, "size": 5, "eta": 8640000},
        {"hash": "EE", "name": "New", "state": "weird", "progress": 0, "size": 5, "eta": 8640000, "category": ""},
    ])
    async with qbit() as a:
        t1, t2, t3 = await a.torrents()
    assert t1.id == "abcdef" and t1.progress == 42.4 and t1.eta_seconds == 600 and t1.category == "radarr"
    assert t1.source == "qbittorrent" and t1.download_speed == 50
    assert t2.state == "error" and "missing" in t2.error and t2.eta_seconds is None and t2.progress == 100.0
    assert t3.state == "unknown" and t3.category is None


async def test_qbit_unreachable(mock):
    mock.post(f"{QB}/api/v2/auth/login").mock(side_effect=httpx.ConnectError("x"))
    async with qbit() as a:
        s = await a.ping()
    assert not s.ok and "Cannot reach" in s.message


# ================================================================ Bazarr


def bazarr():
    return BazarrAdapter(Connection(ServiceKind.bazarr, BZ, api_key="bk"))


async def test_bazarr_ping_and_bad_key(mock):
    route = mock.get(f"{BZ}/api/system/status").respond(json={"data": {"bazarr_version": "1.4.5"}})
    async with bazarr() as a:
        s = await a.ping()
    assert s.ok and s.version == "1.4.5" and route.calls.last.request.headers["X-API-KEY"] == "bk"
    mock.get(f"{BZ}/api/system/status").respond(401)
    async with bazarr() as a:
        s = await a.ping()
    assert not s.ok and s.issues[0].fix


async def test_bazarr_health(mock):
    mock.get(f"{BZ}/api/system/health").respond(json={"data": [
        {"object": "Radarr", "issue": "Could not connect to Radarr"}]})
    async with bazarr() as a:
        (i,) = await a.health_issues()
    assert "Could not connect to Radarr" in i.message and i.fix


async def test_bazarr_wanted(mock):
    mock.get(f"{BZ}/api/movies/wanted").respond(json={"data": [
        {"title": "Dune", "radarrId": 5, "missing_subtitles": [{"name": "English", "code2": "en"}]}], "total": 1})
    mock.get(f"{BZ}/api/episodes/wanted").respond(json={"data": [
        {"seriesTitle": "Severance", "episode_number": "1x2", "episodeTitle": "Half Loop", "sonarrEpisodeId": 77,
         "missing_subtitles": ["French"]}], "total": 1})
    async with bazarr() as a:
        movie, ep = await a.wanted()
    assert (movie.media_type, movie.title, movie.missing_languages, movie.external_id) == \
           ("movie", "Dune", ["English"], 5)
    assert ep.episode == "S01E02 - Half Loop" and ep.external_id == 77 and ep.missing_languages == ["French"]


async def test_bazarr_search_all_missing(mock):
    route = mock.post(f"{BZ}/api/system/tasks").respond(204)
    async with bazarr() as a:
        await a.search_all_missing()
    ids = [c.request.url.params["taskid"] for c in route.calls]
    assert ids == ["wanted_search_missing_subtitles_movies", "wanted_search_missing_subtitles_series"]


async def test_bazarr_arr_connection_form_fields(mock):
    mock.get(f"{BZ}/api/system/settings").respond(json={"general": {"use_radarr": False}, "radarr": {}})
    post = mock.post(f"{BZ}/api/system/settings").respond(204)
    async with bazarr() as a:
        await a.ensure_arr_connection(kind="radarr", host="radarr", port=7878, api_key="RK")
    assert post.calls.last.request.headers["content-type"].startswith("application/x-www-form-urlencoded")
    assert form(post) == {
        "settings-general-use_radarr": ["true"], "settings-radarr-ip": ["radarr"], "settings-radarr-port": ["7878"],
        "settings-radarr-apikey": ["RK"], "settings-radarr-base_url": ["/"], "settings-radarr-ssl": ["false"]}


async def test_bazarr_arr_connection_skips_when_same(mock):
    mock.get(f"{BZ}/api/system/settings").respond(json={
        "general": {"use_sonarr": True},
        "sonarr": {"ip": "sonarr", "port": 8989, "apikey": "SK", "base_url": "/", "ssl": False}})
    post = mock.post(f"{BZ}/api/system/settings")
    async with bazarr() as a:
        await a.ensure_arr_connection(kind="sonarr", host="sonarr", port=8989, api_key="SK")
    assert not post.called


async def test_bazarr_language_profile_creates_and_never_raises(mock):
    mock.get(f"{BZ}/api/system/languages/profiles").respond(json=[])
    post = mock.post(f"{BZ}/api/system/settings").respond(204)
    async with bazarr() as a:
        await a.ensure_default_language_profile(["en"])
    f = form(post)
    profiles = json.loads(f["languages-profiles"][0])
    assert profiles[0]["profileId"] == 1 and profiles[0]["items"][0]["language"] == "en"
    assert f["settings-general-serie_default_profile"] == ["1"] and f["languages-enabled"] == ["en"]
    mock.get(f"{BZ}/api/system/languages/profiles").respond(500)
    async with bazarr() as a:
        await a.ensure_default_language_profile(["fr"])  # must not raise


# ================================================================ Jellyfin


def jellyfin(key=None):
    return JellyfinAdapter(Connection(ServiceKind.jellyfin, JF, api_key=key))


async def test_jellyfin_ping_with_and_without_key(mock):
    info = mock.get(f"{JF}/System/Info").respond(json={"Version": "10.10.3"})
    pub = mock.get(f"{JF}/System/Info/Public").respond(json={"Version": "10.10.3", "StartupWizardCompleted": True})
    async with jellyfin("KEY") as a:
        s = await a.ping()
    assert s.ok and s.version == "10.10.3"
    auth = info.calls.last.request.headers["Authorization"]
    assert auth.startswith('MediaBrowser Client="Unifierr", Device="Unifierr", DeviceId="unifierr"')
    assert auth.endswith('Token="KEY"')
    async with jellyfin() as a:
        assert (await a.ping()).ok
    assert "Token" not in pub.calls.last.request.headers["Authorization"]


async def test_jellyfin_bad_key(mock):
    mock.get(f"{JF}/System/Info").respond(401)
    async with jellyfin("bad") as a:
        s = await a.ping()
    assert not s.ok and s.issues[0].fix


async def test_jellyfin_startup_needed(mock):
    mock.get(f"{JF}/System/Info/Public").respond(json={"StartupWizardCompleted": False})
    async with jellyfin() as a:
        assert await a.startup_needed() is True
    mock.get(f"{JF}/System/Info/Public").respond(json={"StartupWizardCompleted": True})
    async with jellyfin() as a:
        assert await a.startup_needed() is False


async def test_jellyfin_wizard_call_sequence(mock):
    seen = []
    for method, path in [("POST", "/Startup/Configuration"), ("GET", "/Startup/User"), ("POST", "/Startup/User"),
                         ("POST", "/Startup/RemoteAccess"), ("POST", "/Startup/Complete")]:
        mock.route(method=method, url=f"{JF}{path}").mock(
            side_effect=lambda r: (seen.append((r.method, r.url.path, r.content)), httpx.Response(204))[1])
    async with jellyfin("ignored") as a:
        await a.run_startup_wizard("admin", "pw123")
    assert [(m, p) for m, p, _ in seen] == [
        ("POST", "/Startup/Configuration"), ("GET", "/Startup/User"), ("POST", "/Startup/User"),
        ("POST", "/Startup/RemoteAccess"), ("POST", "/Startup/Complete")]
    assert json.loads(seen[0][2]) == {"UICulture": "en-US", "MetadataCountryCode": "US",
                                      "PreferredMetadataLanguage": "en"}
    assert json.loads(seen[2][2]) == {"Name": "admin", "Password": "pw123"}
    assert json.loads(seen[3][2]) == {"EnableRemoteAccess": True, "EnableAutomaticPortMapping": False}


async def test_jellyfin_authenticate_and_create_api_key(mock):
    auth = mock.post(f"{JF}/Users/AuthenticateByName").respond(json={"AccessToken": "TOK", "User": {}})
    created = mock.post(f"{JF}/Auth/Keys").respond(204)
    mock.get(f"{JF}/Auth/Keys").respond(json={"Items": [
        {"AccessToken": "OLD", "AppName": "Unifierr", "DateCreated": "2026-01-01T00:00:00.0000000Z"},
        {"AccessToken": "NEW", "AppName": "Unifierr", "DateCreated": "2026-11-07T10:00:00.0000000Z"},
        {"AccessToken": "OTHER", "AppName": "Sonarr", "DateCreated": "2026-12-01T00:00:00.0000000Z"}]})
    async with jellyfin() as a:
        token = await a.authenticate("admin", "pw")
        a.conn.api_key = token
        key = await a.create_api_key("Unifierr")
    assert json.loads(auth.calls.last.request.content) == {"Username": "admin", "Pw": "pw"}
    assert token == "TOK" and key == "NEW"
    assert created.calls.last.request.url.params["App"] == "Unifierr"
    assert created.calls.last.request.headers["Authorization"].endswith('Token="TOK"')


async def test_jellyfin_create_api_key_missing(mock):
    mock.post(f"{JF}/Auth/Keys").respond(204)
    mock.get(f"{JF}/Auth/Keys").respond(json={"Items": []})
    async with jellyfin("TOK") as a:
        with pytest.raises(ServiceUnavailable):
            await a.create_api_key()


async def test_jellyfin_ensure_library_creates(mock):
    mock.get(f"{JF}/Library/VirtualFolders").mock(side_effect=[
        httpx.Response(200, json=[]),
        httpx.Response(200, json=[{"Name": "Movies", "CollectionType": "movies", "ItemId": "abc",
                                   "Locations": ["/data/media/movies"]}])])
    post = mock.post(f"{JF}/Library/VirtualFolders").respond(204)
    async with jellyfin("K") as a:
        lib = await a.ensure_library("Movies", "movies", "/data/media/movies")
    q = post.calls.last.request.url.params
    assert (q["name"], q["collectionType"], q["refreshLibrary"], q["paths"]) == \
           ("Movies", "movies", "true", "/data/media/movies")
    assert json.loads(post.calls.last.request.content) == {"LibraryOptions": {}}
    assert lib.id == "abc" and lib.type == "movies" and lib.paths == ["/data/media/movies"]


async def test_jellyfin_ensure_library_existing_path_no_post(mock):
    mock.get(f"{JF}/Library/VirtualFolders").respond(json=[
        {"Name": "Films", "CollectionType": "movies", "ItemId": "x", "Locations": ["/data/media/movies/"]}])
    post = mock.post(f"{JF}/Library/VirtualFolders")
    async with jellyfin("K") as a:
        lib = await a.ensure_library("Movies", "movies", "/data/media/movies")
        libs = await a.libraries()
    assert lib.name == "Films" and not post.called and libs[0].id == "x"


async def test_jellyfin_refresh_and_recent(mock):
    refresh = mock.post(f"{JF}/Library/Refresh").respond(204)
    items = mock.get(f"{JF}/Items").respond(json={"Items": [
        {"Name": "Dune", "Type": "Movie", "ProductionYear": 2021, "Overview": "Sand",
         "ProviderIds": {"Tmdb": "438631", "Imdb": "tt1160419"}},
        {"Name": "Severance", "Type": "Series", "ProviderIds": {"Tvdb": "371980"}}]})
    async with jellyfin("K") as a:
        await a.refresh_library()
        movie, show = await a.recently_added(5)
    assert refresh.called and items.calls.last.request.url.params["Limit"] == "5"
    assert movie.tmdb_id == 438631 and movie.imdb_id == "tt1160419" and movie.poster_url is None
    assert show.media_type == "series" and show.tvdb_id == 371980


# ================================================================ Plex


def plex(key="PT"):
    return PlexAdapter(Connection(ServiceKind.plex, PX, api_key=key))


async def test_plex_ping_ok_and_bad_token(mock):
    ident = mock.get(f"{PX}/identity").respond(json={"MediaContainer": {"version": "1.41.3", "claimed": True}})
    root = mock.get(f"{PX}/").respond(json={"MediaContainer": {}})
    async with plex() as a:
        s = await a.ping()
    assert s.ok and s.version == "1.41.3"
    h = root.calls.last.request.headers
    assert h["X-Plex-Token"] == "PT" and h["Accept"] == "application/json" and h["X-Plex-Client-Identifier"]
    assert ident.called
    mock.get(f"{PX}/").respond(401)
    async with plex("bad") as a:
        s = await a.ping()
    assert not s.ok and s.issues[0].fix


SECTIONS = {"MediaContainer": {"Directory": [
    {"key": "1", "title": "Films", "type": "movie", "Location": [{"id": 1, "path": "/data/media/movies"}]}]}}


async def test_plex_ensure_library_existing_no_post(mock):
    mock.get(f"{PX}/library/sections").respond(json=SECTIONS)
    post = mock.post(f"{PX}/library/sections")
    async with plex() as a:
        lib = await a.ensure_library("Movies", "movies", "/data/media/movies/")
        assert (await a.libraries())[0].type == "movies"
    assert lib.id == "1" and lib.type == "movies" and not post.called


async def test_plex_ensure_library_creates_show_library(mock):
    mock.get(f"{PX}/library/sections").respond(json=SECTIONS)
    post = mock.post(f"{PX}/library/sections").respond(json={"MediaContainer": {"Directory": [
        {"key": "2", "title": "TV Shows", "type": "show", "Location": [{"path": "/data/media/tv"}]}]}})
    async with plex() as a:
        lib = await a.ensure_library("TV Shows", "tvshows", "/data/media/tv")
    q = post.calls.last.request.url.params
    assert q["name"] == "TV Shows" and q["type"] == "show" and q["agent"] == "tv.plex.agents.series"
    assert q["scanner"] == "Plex TV Series" and q["language"] == "en-US" and q["location"] == "/data/media/tv"
    assert post.calls.last.request.headers["X-Plex-Token"] == "PT"
    assert lib.id == "2" and lib.type == "tvshows" and lib.paths == ["/data/media/tv"]


async def test_plex_ensure_movie_library_agent(mock):
    mock.get(f"{PX}/library/sections").respond(json={"MediaContainer": {}})
    post = mock.post(f"{PX}/library/sections").respond(json={"MediaContainer": {}})
    mock.get(f"{PX}/library/sections").respond(json={"MediaContainer": {}})
    async with plex() as a:
        lib = await a.ensure_library("Movies", "movies", "/data/media/movies")
    q = post.calls.last.request.url.params
    assert q["type"] == "movie" and q["agent"] == "tv.plex.agents.movie" and q["scanner"] == "Plex Movie"
    assert lib.name == "Movies"


async def test_plex_unsupported_type(mock):
    async with plex() as a:
        with pytest.raises(ServiceUnavailable):
            await a.ensure_library("Music", "music", "/m")


async def test_plex_refresh_and_recent(mock):
    refresh = mock.get(f"{PX}/library/sections/all/refresh").respond(200)
    mock.get(f"{PX}/library/recentlyAdded").respond(json={"MediaContainer": {"Metadata": [
        {"type": "movie", "title": "Dune", "year": 2021, "summary": "Sand", "Guid": [{"id": "tmdb://438631"},
                                                                                   {"id": "imdb://tt1160419"}]},
        {"type": "episode", "title": "Half Loop", "grandparentTitle": "Severance",
         "Guid": [{"id": "tvdb://371980"}]},
        {"type": "episode", "title": "Ep 2", "grandparentTitle": "Severance"},
        {"type": "artist", "title": "Band"}]}})
    async with plex() as a:
        await a.refresh_library()
        items = await a.recently_added(10)
    assert refresh.called and [i.title for i in items] == ["Dune", "Severance"]
    assert items[0].tmdb_id == 438631 and items[0].imdb_id == "tt1160419" and items[0].poster_url is None
    assert items[1].media_type == "series"


# ================================================================ registry


def test_registry_covers_every_kind():
    assert set(ADAPTERS) == set(ServiceKind)
    for kind in ServiceKind:
        a = get_adapter(Connection(kind, "http://x:1"))
        assert a.kind == kind and a.display_name and a.default_port


async def test_registry_uses_given_client_and_does_not_close_it():
    client = httpx.AsyncClient()
    a = get_adapter(Connection(ServiceKind.radarr, "http://x:1"), client)
    assert a.client is client
    await a.aclose()
    assert not client.is_closed
    await client.aclose()
