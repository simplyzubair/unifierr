import json

import httpx

from app.adapters.base import Connection, ServiceKind
from app.adapters.prowlarr import ProwlarrAdapter
from app.adapters.radarr import RadarrAdapter
from app.adapters.sonarr import SonarrAdapter

RADARR = "http://radarr:7878"
SONARR = "http://sonarr:8989"
PROWLARR = "http://prowlarr:9696"


def radarr():
    return RadarrAdapter(Connection(ServiceKind.radarr, RADARR, api_key="k"))


def sonarr():
    return SonarrAdapter(Connection(ServiceKind.sonarr, SONARR, api_key="k"))


def prowlarr():
    return ProwlarrAdapter(Connection(ServiceKind.prowlarr, PROWLARR, api_key="k"))


def body(route) -> dict:
    return json.loads(route.calls.last.request.content)


def field(entry: dict, name: str):
    return next(f["value"] for f in entry["fields"] if f["name"] == name)


# ---------------------------------------------------------------- ping / health


async def test_ping_ok_sends_api_key(mock):
    route = mock.get(f"{RADARR}/api/v3/system/status").respond(json={"appName": "Radarr", "version": "5.14.0.9383"})
    async with radarr() as a:
        s = await a.ping()
    assert s.ok and s.version == "5.14.0.9383"
    assert route.calls.last.request.headers["X-Api-Key"] == "k"


async def test_ping_bad_key_returns_not_ok_with_fix(mock):
    mock.get(f"{SONARR}/api/v3/system/status").respond(401, json={"error": "Unauthorized"})
    async with sonarr() as a:
        s = await a.ping()
        assert not s.ok and not await a.api_key_valid()
    assert "rejected" in s.message
    assert s.issues[0].severity == "error" and s.issues[0].fix


async def test_ping_connection_refused_does_not_raise(mock):
    mock.get(f"{PROWLARR}/api/v1/system/status").mock(side_effect=httpx.ConnectError("refused"))
    async with prowlarr() as a:
        s = await a.ping()
    assert not s.ok and "Cannot reach" in s.message


async def test_ping_html_page_is_friendly(mock):
    mock.get(f"{RADARR}/api/v3/system/status").respond(200, text="<html>login</html>")
    async with radarr() as a:
        s = await a.ping()
    assert not s.ok


async def test_health_issues_translated(mock):
    mock.get(f"{RADARR}/api/v3/health").respond(json=[
        {"source": "IndexerStatusCheck", "type": "warning", "message": "Indexers unavailable due to failures: X"},
        {"source": "RootFolderCheck", "type": "error", "message": "Missing root folder: /data/media/movies"},
        {"source": "SomethingNew", "type": "notice", "message": "Hello"},
        {"source": "Fine", "type": "ok", "message": "ignored"},
    ])
    async with radarr() as a:
        issues = await a.health_issues()
    assert [i.severity for i in issues] == ["warning", "error", "info"]
    assert issues[0].explanation and issues[0].fix and issues[0].source == "radarr"
    assert issues[2].explanation is None and issues[2].message == "Hello"


# ---------------------------------------------------------------- radarr media


MOVIE_LOOKUP = {
    "title": "The Matrix", "year": 1999, "overview": "A hacker.", "tmdbId": 603, "imdbId": "tt0133093",
    "status": "released", "id": 0,
    "images": [
        {"coverType": "poster", "url": "/MediaCover/0/poster.jpg",
         "remoteUrl": "https://image.tmdb.org/t/p/original/poster.jpg"},
        {"coverType": "fanart", "remoteUrl": "https://image.tmdb.org/t/p/original/fan.jpg"},
    ],
}


async def test_lookup_maps_poster_and_flags(mock):
    in_lib = {**MOVIE_LOOKUP, "id": 7, "hasFile": True, "monitored": True, "sizeOnDisk": 1234}
    http_poster = {**MOVIE_LOOKUP, "title": "B", "images": [{"coverType": "poster", "remoteUrl": "http://x/p.jpg"}]}
    route = mock.get(f"{RADARR}/api/v3/movie/lookup").respond(json=[MOVIE_LOOKUP, in_lib, http_poster])
    async with radarr() as a:
        items = await a.lookup("matrix")
    assert route.calls.last.request.url.params["term"] == "matrix"
    new, old, odd = items
    assert new.poster_url == "https://image.tmdb.org/t/p/original/poster.jpg"
    assert not new.in_library and new.external_id is None and not new.has_file
    assert old.in_library and old.external_id == 7 and old.has_file and old.monitored and old.size_on_disk == 1234
    assert odd.poster_url is None  # not https


async def test_add_movie_defaults_and_payload(mock):
    mock.get(f"{RADARR}/api/v3/movie/lookup/tmdb").respond(json=MOVIE_LOOKUP)
    mock.get(f"{RADARR}/api/v3/rootfolder").respond(json=[{"id": 1, "path": "/data/media/movies"}])
    mock.get(f"{RADARR}/api/v3/qualityprofile").respond(json=[{"id": 4, "name": "HD-1080p"}, {"id": 5, "name": "x"}])
    post = mock.post(f"{RADARR}/api/v3/movie").respond(json={**MOVIE_LOOKUP, "id": 9, "monitored": True})
    async with radarr() as a:
        item = await a.add_movie(603)
    sent = body(post)
    assert sent["qualityProfileId"] == 4 and sent["rootFolderPath"] == "/data/media/movies"
    assert sent["monitored"] is True and sent["addOptions"]["searchForMovie"] is True
    assert item.external_id == 9 and item.in_library


async def test_add_movie_explicit_args_and_no_search(mock):
    mock.get(f"{RADARR}/api/v3/movie/lookup/tmdb").respond(json=MOVIE_LOOKUP)
    post = mock.post(f"{RADARR}/api/v3/movie").respond(json={**MOVIE_LOOKUP, "id": 9})
    async with radarr() as a:
        await a.add_movie(603, root_folder="/movies", quality_profile_id=2, search=False)
    sent = body(post)
    assert sent["rootFolderPath"] == "/movies" and sent["qualityProfileId"] == 2
    assert sent["addOptions"]["searchForMovie"] is False


async def test_add_movie_already_in_library_returns_it(mock):
    mock.get(f"{RADARR}/api/v3/movie/lookup/tmdb").respond(json={**MOVIE_LOOKUP, "id": 3})
    post = mock.post(f"{RADARR}/api/v3/movie")
    async with radarr() as a:
        item = await a.add_movie(603)
    assert item.external_id == 3 and not post.called


async def test_delete_movie(mock):
    route = mock.delete(f"{RADARR}/api/v3/movie/3").respond(200, json={})
    async with radarr() as a:
        await a.delete_movie(3, delete_files=True)
    assert route.calls.last.request.url.params["deleteFiles"] == "true"


# ---------------------------------------------------------------- sonarr media


SERIES_LOOKUP = {
    "title": "Severance", "year": 2022, "tvdbId": 371980, "tmdbId": 95396, "imdbId": "tt11280740",
    "status": "continuing", "seriesType": "standard", "id": 0,
    "images": [{"coverType": "poster", "remoteUrl": "https://artworks.thetvdb.com/p.jpg"}],
}


async def test_sonarr_list_series_statistics(mock):
    mock.get(f"{SONARR}/api/v3/series").respond(json=[
        {**SERIES_LOOKUP, "id": 2, "monitored": True,
         "statistics": {"episodeFileCount": 9, "episodeCount": 9, "percentOfEpisodes": 100.0, "sizeOnDisk": 5}},
        {**SERIES_LOOKUP, "title": "Empty", "id": 3,
         "statistics": {"episodeFileCount": 0, "percentOfEpisodes": 0.0}},
    ])
    async with sonarr() as a:
        full, empty = await a.list_series()
    assert full.has_file and full.percent_complete == 100.0 and full.external_id == 2
    assert full.tvdb_id == 371980 and full.poster_url.startswith("https://")
    assert not empty.has_file and empty.percent_complete == 0.0


async def test_add_series_v4_has_no_language_profile(mock):
    lookup = mock.get(f"{SONARR}/api/v3/series/lookup").respond(json=[SERIES_LOOKUP])
    mock.get(f"{SONARR}/api/v3/languageprofile").respond(404)
    mock.get(f"{SONARR}/api/v3/rootfolder").respond(json=[{"id": 1, "path": "/data/media/tv"}])
    mock.get(f"{SONARR}/api/v3/qualityprofile").respond(json=[{"id": 1, "name": "Any"}])
    post = mock.post(f"{SONARR}/api/v3/series").respond(json={**SERIES_LOOKUP, "id": 5})
    async with sonarr() as a:
        item = await a.add_series(371980)
    assert lookup.calls.last.request.url.params["term"] == "tvdb:371980"
    sent = body(post)
    assert "languageProfileId" not in sent and sent["seasonFolder"] is True
    assert sent["addOptions"] == {"monitor": "all", "searchForMissingEpisodes": True,
                                  "searchForCutoffUnmetEpisodes": False}
    assert item.external_id == 5


async def test_add_series_v3_sends_language_profile(mock):
    mock.get(f"{SONARR}/api/v3/series/lookup").respond(json=[SERIES_LOOKUP])
    mock.get(f"{SONARR}/api/v3/languageprofile").respond(json=[{"id": 1, "name": "English"}])
    post = mock.post(f"{SONARR}/api/v3/series").respond(json={**SERIES_LOOKUP, "id": 5})
    async with sonarr() as a:
        await a.add_series(371980, root_folder="/tv", quality_profile_id=3, monitor="firstSeason", search=False)
    sent = body(post)
    assert sent["languageProfileId"] == 1 and sent["rootFolderPath"] == "/tv"
    assert sent["addOptions"]["monitor"] == "firstSeason" and sent["addOptions"]["searchForMissingEpisodes"] is False


async def test_add_series_existing_not_posted(mock):
    mock.get(f"{SONARR}/api/v3/series/lookup").respond(json=[{**SERIES_LOOKUP, "id": 8}])
    post = mock.post(f"{SONARR}/api/v3/series")
    async with sonarr() as a:
        item = await a.add_series(371980)
    assert item.external_id == 8 and not post.called


# ---------------------------------------------------------------- root folders / disk


async def test_ensure_root_folder_idempotent(mock):
    mock.get(f"{RADARR}/api/v3/rootfolder").respond(json=[{"id": 1, "path": "/data/media/movies/", "accessible": True}])
    post = mock.post(f"{RADARR}/api/v3/rootfolder")
    async with radarr() as a:
        r = await a.ensure_root_folder("/data/media/movies")
    assert r["id"] == 1 and not post.called


async def test_ensure_root_folder_creates(mock):
    mock.get(f"{RADARR}/api/v3/rootfolder").respond(json=[])
    post = mock.post(f"{RADARR}/api/v3/rootfolder").respond(json={"id": 2, "path": "/data/media/movies"})
    async with radarr() as a:
        r = await a.ensure_root_folder("/data/media/movies")
    assert body(post) == {"path": "/data/media/movies"} and r["id"] == 2


async def test_disk_space(mock):
    mock.get(f"{SONARR}/api/v3/diskspace").respond(json=[
        {"path": "/data", "label": "data", "freeSpace": 100, "totalSpace": 1000}])
    async with sonarr() as a:
        (d,) = await a.disk_space()
    assert (d.path, d.free_bytes, d.total_bytes) == ("/data", 100, 1000)


# ---------------------------------------------------------------- download client


def qbit_schema(category_field: str):
    return [
        {"implementation": "Transmission", "fields": []},
        {"implementation": "QBittorrent", "implementationName": "qBittorrent", "protocol": "torrent",
         "enable": False, "priority": 1, "removeCompletedDownloads": True, "tags": [],
         "fields": [
             {"name": "host", "value": "localhost"}, {"name": "port", "value": 8080},
             {"name": "useSsl", "value": False}, {"name": "username", "value": None},
             {"name": "password", "value": None, "privacy": "password"},
             {"name": category_field, "value": category_field.replace("Category", "")},
             {"name": "initialState", "value": 0},
         ]},
    ]


async def test_ensure_qbittorrent_client_creates_radarr(mock):
    mock.get(f"{RADARR}/api/v3/downloadclient").respond(json=[])
    mock.get(f"{RADARR}/api/v3/downloadclient/schema").respond(json=qbit_schema("movieCategory"))
    post = mock.post(f"{RADARR}/api/v3/downloadclient").respond(json={"id": 1})
    async with radarr() as a:
        await a.ensure_qbittorrent_client(host="qbittorrent", port=8080, username="u", password="p",
                                          category="radarr")
    sent = body(post)
    assert post.calls.last.request.url.params["forceSave"] == "true"
    assert sent["implementation"] == "QBittorrent" and sent["enable"] is True and sent["name"] == "qBittorrent"
    assert (field(sent, "host"), field(sent, "port"), field(sent, "username"), field(sent, "password")) == \
           ("qbittorrent", 8080, "u", "p")
    assert field(sent, "movieCategory") == "radarr" and field(sent, "initialState") == 0
    assert "tvCategory" not in {f["name"] for f in sent["fields"]}


async def test_ensure_qbittorrent_client_sonarr_uses_tv_category(mock):
    mock.get(f"{SONARR}/api/v3/downloadclient").respond(json=[])
    mock.get(f"{SONARR}/api/v3/downloadclient/schema").respond(json=qbit_schema("tvCategory"))
    post = mock.post(f"{SONARR}/api/v3/downloadclient").respond(json={"id": 1})
    async with sonarr() as a:
        await a.ensure_qbittorrent_client(host="qbittorrent", port=8080, username="u", password="p",
                                          category="tv-sonarr")
    assert field(body(post), "tvCategory") == "tv-sonarr"


def existing_qbit(**over):
    e = {"id": 4, "name": "qBittorrent", "implementation": "QBittorrent", "enable": True, "fields": [
        {"name": "host", "value": "qbittorrent"}, {"name": "port", "value": 8080}, {"name": "useSsl", "value": False},
        {"name": "username", "value": "u"}, {"name": "password", "value": "********"},
        {"name": "movieCategory", "value": "radarr"}]}
    e["fields"] = [{**f, **over.get(f["name"], {})} for f in e["fields"]]
    return e


async def test_ensure_qbittorrent_client_existing_is_reused_and_secret_refreshed(mock):
    mock.get(f"{RADARR}/api/v3/downloadclient").respond(json=[existing_qbit()])
    post = mock.post(f"{RADARR}/api/v3/downloadclient")
    put = mock.put(f"{RADARR}/api/v3/downloadclient/4").respond(json={"id": 4})
    async with radarr() as a:
        r = await a.ensure_qbittorrent_client(host="qbittorrent", port=8080, username="u", password="p",
                                              category="radarr")
    # No duplicate; the masked password is re-sent because it cannot be compared.
    assert r["id"] == 4 and not post.called and field(body(put), "password") == "p"


async def test_ensure_qbittorrent_client_updates_when_different(mock):
    mock.get(f"{RADARR}/api/v3/downloadclient").respond(json=[existing_qbit(movieCategory={"value": "old"})])
    put = mock.put(f"{RADARR}/api/v3/downloadclient/4").respond(json={"id": 4})
    async with radarr() as a:
        await a.ensure_qbittorrent_client(host="qbittorrent", port=8080, username="u", password="p",
                                          category="radarr")
    sent = body(put)
    assert field(sent, "movieCategory") == "radarr" and sent["id"] == 4
    assert field(sent, "password") == "p"  # the real secret is sent, never the mask
    assert put.calls.last.request.url.params["forceSave"] == "true"


# ---------------------------------------------------------------- notifications


def notif_schema(ts_extra=()):
    base = {"supportsOnDownload": True, "supportsOnUpgrade": True, "supportsOnRename": True,
            "onGrab": False, "onDownload": False, "onUpgrade": False, "onRename": False}
    return [
        {**base, "implementation": "MediaBrowser", "implementationName": "Emby / Jellyfin", "fields": [
            {"name": "host", "value": ""}, {"name": "port", "value": 8096}, {"name": "useSsl", "value": False},
            {"name": "apiKey", "value": ""}, {"name": "updateLibrary", "value": False}]},
        {**base, "implementation": "PlexServer", "fields": [
            {"name": "host", "value": ""}, {"name": "port", "value": 32400}, {"name": "useSsl", "value": False},
            {"name": "authToken", "value": ""}, {"name": "updateLibrary", "value": False}], **dict(ts_extra)},
    ]


async def test_jellyfin_notification_created(mock):
    mock.get(f"{RADARR}/api/v3/notification").respond(json=[])
    mock.get(f"{RADARR}/api/v3/notification/schema").respond(json=notif_schema())
    post = mock.post(f"{RADARR}/api/v3/notification").respond(json={"id": 1})
    async with radarr() as a:
        await a.ensure_media_server_notification(kind="jellyfin", host="jellyfin", port=8096, api_key="JK")
    sent = body(post)
    assert sent["implementation"] == "MediaBrowser" and sent["name"] == "Jellyfin"
    assert field(sent, "host") == "jellyfin" and field(sent, "apiKey") == "JK" and field(sent, "updateLibrary") is True
    assert sent["onDownload"] is True and sent["onUpgrade"] is True and sent["onGrab"] is False
    assert "onMovieDelete" not in sent
    assert post.calls.last.request.url.params["forceSave"] == "true"


async def test_plex_notification_uses_auth_token_and_respects_unsupported_flag(mock):
    mock.get(f"{SONARR}/api/v3/notification").respond(json=[])
    mock.get(f"{SONARR}/api/v3/notification/schema").respond(json=notif_schema({"supportsOnRename": False}.items()))
    post = mock.post(f"{SONARR}/api/v3/notification").respond(json={"id": 1})
    async with sonarr() as a:
        await a.ensure_media_server_notification(kind="plex", host="plex", port=32400, api_key="PT", use_ssl=True)
    sent = body(post)
    assert sent["implementation"] == "PlexServer" and field(sent, "authToken") == "PT"
    assert field(sent, "useSsl") is True and sent["onRename"] is False


async def test_notification_idempotent_by_host(mock):
    existing = {"id": 3, "implementation": "MediaBrowser", "fields": [
        {"name": "host", "value": "jellyfin"}, {"name": "port", "value": 8096}, {"name": "useSsl", "value": False},
        {"name": "apiKey", "value": "********"}, {"name": "updateLibrary", "value": True}]}
    mock.get(f"{RADARR}/api/v3/notification").respond(json=[existing])
    post = mock.post(f"{RADARR}/api/v3/notification")
    put = mock.put(f"{RADARR}/api/v3/notification/3").respond(json={"id": 3})
    async with radarr() as a:
        r = await a.ensure_media_server_notification(kind="jellyfin", host="jellyfin", port=8096, api_key="JK")
    assert r["id"] == 3 and not post.called and field(body(put), "apiKey") == "JK"


# ---------------------------------------------------------------- queue


async def test_radarr_queue_mapping(mock):
    route = mock.get(f"{RADARR}/api/v3/queue").respond(json={"totalRecords": 4, "records": [
        {"id": 11, "downloadId": "ABCDEF0123", "title": "The.Matrix.1999.1080p", "size": 1000, "sizeleft": 250,
         "status": "downloading", "trackedDownloadStatus": "ok", "trackedDownloadState": "downloading",
         "timeleft": "00:12:34", "movie": {"title": "The Matrix"}, "statusMessages": []},
        {"id": 12, "downloadId": "FFFF", "title": "Done", "size": 100, "sizeleft": 0, "status": "completed",
         "trackedDownloadStatus": "ok", "trackedDownloadState": "importPending", "movie": {"title": "Done Movie"}},
        {"id": 13, "title": "Broken", "size": 100, "sizeleft": 100, "status": "warning",
         "trackedDownloadStatus": "warning", "trackedDownloadState": "importBlocked",
         "statusMessages": [{"title": "Broken", "messages": ["No files found are eligible for import",
                                                                 "Sample file"]}]},
        {"id": 14, "title": "Err", "size": 0, "sizeleft": 0, "status": "failed", "errorMessage": "Disk full",
         "timeleft": "1.01:00:00"},
    ]})
    async with radarr() as a:
        dl, imp, blocked, failed = await a.queue()
    params = route.calls.last.request.url.params
    assert params["includeMovie"] == "true" and params["pageSize"] == "200"
    assert dl.id == "abcdef0123" and dl.state == "downloading" and dl.progress == 75.0
    assert dl.media_title == "The Matrix" and dl.media_type == "movie" and dl.source == "radarr"
    assert dl.eta_seconds == 754 and dl.size == 1000 and dl.downloaded == 750
    assert imp.state == "importing" and imp.progress == 100.0
    assert blocked.id == "radarr:13" and blocked.state == "error"
    assert blocked.error == "No files found are eligible for import; Sample file"
    assert failed.state == "error" and failed.error == "Disk full" and failed.eta_seconds == 90000


async def test_sonarr_queue_uses_series_title(mock):
    route = mock.get(f"{SONARR}/api/v3/queue").respond(json={"records": [
        {"id": 1, "downloadId": "AA", "title": "Severance.S01E01", "size": 10, "sizeleft": 5, "status": "paused",
         "series": {"title": "Severance"}}]})
    async with sonarr() as a:
        (q,) = await a.queue()
    assert route.calls.last.request.url.params["includeSeries"] == "true"
    assert q.media_title == "Severance" and q.media_type == "series" and q.state == "paused" and q.source == "sonarr"


# ---------------------------------------------------------------- prowlarr


async def test_prowlarr_indexers_with_status(mock):
    mock.get(f"{PROWLARR}/api/v1/indexer").respond(json=[
        {"id": 1, "name": "1337x", "protocol": "torrent", "enable": True, "privacy": "public",
         "implementation": "Cardigann"},
        {"id": 2, "name": "Down", "protocol": "torrent", "enable": True, "privacy": "private"},
        {"id": 3, "name": "Off", "protocol": "usenet", "enable": False}])
    mock.get(f"{PROWLARR}/api/v1/indexerstatus").respond(json=[
        {"indexerId": 2, "disabledTill": "2026-11-07T12:00:00Z"}])
    async with prowlarr() as a:
        ok, down, off = await a.indexers()
    assert ok.status == "ok" and ok.privacy == "public" and ok.implementation == "Cardigann"
    assert down.status.startswith("disabled until 2026-11-07 12:00")
    assert not off.enabled and off.status == "disabled"


async def test_prowlarr_schemas_required_fields(mock):
    mock.get(f"{PROWLARR}/api/v1/indexer/schema").respond(json=[
        {"name": "1337x", "definitionName": "1337x", "implementation": "Cardigann", "protocol": "torrent",
         "privacy": "public", "description": "d", "language": "en-US", "fields": [
             {"name": "definitionFile", "type": "textbox", "value": "1337x"},
             {"name": "username", "label": "Username", "type": "textbox", "value": ""},
             {"name": "baseSettings.limitsUnit", "type": "select", "value": 0},
             {"name": "extra", "type": "textbox", "advanced": True}]}])
    async with prowlarr() as a:
        (s,) = await a.indexer_schemas()
    assert s.name == "1337x" and s.implementation == "Cardigann"
    assert [f["name"] for f in s.required_fields] == ["username"]


async def test_prowlarr_add_indexer(mock):
    schema = {"name": "1337x", "definitionName": "1337x", "implementation": "Cardigann", "protocol": "torrent",
              "enable": False, "appProfileId": 0, "fields": [{"name": "username", "value": ""}]}
    mock.get(f"{PROWLARR}/api/v1/indexer").respond(json=[])
    mock.get(f"{PROWLARR}/api/v1/indexer/schema").respond(json=[schema])
    mock.get(f"{PROWLARR}/api/v1/appprofile").respond(json=[{"id": 1}])
    post = mock.post(f"{PROWLARR}/api/v1/indexer").respond(json={**schema, "id": 10, "enable": True})
    async with prowlarr() as a:
        idx = await a.add_indexer("1337X", {"username": "me"})
    sent = body(post)
    assert sent["enable"] is True and sent["appProfileId"] == 1 and field(sent, "username") == "me"
    assert post.calls.last.request.url.params["forceSave"] == "true"
    assert idx.id == 10


async def test_prowlarr_add_indexer_existing_and_unknown(mock):
    mock.get(f"{PROWLARR}/api/v1/indexer").respond(json=[
        {"id": 1, "name": "1337x", "definitionName": "1337x", "protocol": "torrent", "enable": True}])
    mock.get(f"{PROWLARR}/api/v1/indexer/schema").respond(json=[])
    post = mock.post(f"{PROWLARR}/api/v1/indexer")
    async with prowlarr() as a:
        assert (await a.add_indexer("1337x")).id == 1
        assert not post.called
        from app.core.errors import NotFound

        try:
            await a.add_indexer("Nope")
        except NotFound:
            pass
        else:
            raise AssertionError("expected NotFound")


async def test_prowlarr_set_enabled_delete_testall(mock):
    mock.get(f"{PROWLARR}/api/v1/indexer/5").respond(json={"id": 5, "name": "X", "protocol": "torrent",
                                                          "enable": True})
    put = mock.put(f"{PROWLARR}/api/v1/indexer/5").respond(json={"id": 5, "name": "X", "protocol": "torrent",
                                                                "enable": False})
    dele = mock.delete(f"{PROWLARR}/api/v1/indexer/5").respond(200, json={})
    mock.post(f"{PROWLARR}/api/v1/indexer/testall").respond(json=[
        {"id": 1, "isValid": True, "validationFailures": []},
        {"id": 2, "isValid": False,
         "validationFailures": [{"propertyName": "", "errorMessage": "Blocked by Cloudflare"}]}])
    async with prowlarr() as a:
        off = await a.set_indexer_enabled(5, False)
        await a.delete_indexer(5)
        res = await a.test_all_indexers()
    assert body(put)["enable"] is False and not off.enabled and dele.called
    assert res == [{"id": 1, "isValid": True, "errors": []},
                   {"id": 2, "isValid": False, "errors": ["Blocked by Cloudflare"]}]


def app_schema():
    return [{"implementation": "Radarr", "syncLevel": "disabled", "fields": [
        {"name": "prowlarrUrl", "value": ""}, {"name": "baseUrl", "value": ""}, {"name": "apiKey", "value": ""},
        {"name": "syncCategories", "value": [2000, 2010]}]},
        {"implementation": "Sonarr", "syncLevel": "disabled", "fields": [
            {"name": "prowlarrUrl", "value": ""}, {"name": "baseUrl", "value": ""}, {"name": "apiKey", "value": ""}]}]


async def test_prowlarr_ensure_application_creates_full_sync(mock):
    mock.get(f"{PROWLARR}/api/v1/applications").respond(json=[])
    mock.get(f"{PROWLARR}/api/v1/applications/schema").respond(json=app_schema())
    post = mock.post(f"{PROWLARR}/api/v1/applications").respond(json={"id": 1})
    async with prowlarr() as a:
        await a.ensure_application(kind="radarr", app_url="http://radarr:7878", app_api_key="RK",
                                   prowlarr_url="http://prowlarr:9696")
    sent = body(post)
    assert sent["implementation"] == "Radarr" and sent["syncLevel"] == "fullSync" and sent["name"] == "Radarr"
    assert field(sent, "baseUrl") == "http://radarr:7878" and field(sent, "apiKey") == "RK"
    assert field(sent, "prowlarrUrl") == "http://prowlarr:9696" and field(sent, "syncCategories") == [2000, 2010]
    assert post.calls.last.request.url.params["forceSave"] == "true"


async def test_prowlarr_ensure_application_idempotent_and_updates(mock):
    existing = {"id": 2, "implementation": "Radarr", "syncLevel": "fullSync", "fields": [
        {"name": "prowlarrUrl", "value": "http://prowlarr:9696"}, {"name": "baseUrl", "value": "http://radarr:7878"},
        {"name": "apiKey", "value": "********"}]}
    mock.get(f"{PROWLARR}/api/v1/applications").respond(json=[existing])
    post = mock.post(f"{PROWLARR}/api/v1/applications")
    put = mock.put(f"{PROWLARR}/api/v1/applications/2").respond(json={"id": 2})
    async with prowlarr() as a:
        r = await a.ensure_application(kind="radarr", app_url="http://radarr:7878", app_api_key="RK",
                                       prowlarr_url="http://prowlarr:9696")
        assert r["id"] == 2 and field(body(put), "apiKey") == "RK"
        await a.ensure_application(kind="radarr", app_url="http://radarr:7878", app_api_key="RK",
                                   prowlarr_url="http://prowlarr:1234")
    assert not post.called and field(body(put), "prowlarrUrl") == "http://prowlarr:1234"


async def test_prowlarr_reinstalled_app_with_new_address_is_updated_not_duplicated(mock):
    # Found on a real Prowlarr: adding a second app named "Radarr" fails, so a moved/reinstalled
    # Radarr must update the existing entry.
    existing = {"id": 1, "name": "Radarr", "implementation": "Radarr", "fields": [
        {"name": "prowlarrUrl", "value": "http://prowlarr:9696"}, {"name": "baseUrl", "value": "http://127.0.0.1:7878"},
        {"name": "apiKey", "value": "********"}]}
    mock.get(f"{PROWLARR}/api/v1/applications").respond(json=[existing])
    post = mock.post(f"{PROWLARR}/api/v1/applications")
    put = mock.put(f"{PROWLARR}/api/v1/applications/1").respond(json={"id": 1})
    async with prowlarr() as a:
        await a.ensure_application(kind="radarr", app_url="http://radarr:7878", app_api_key="NEWKEY",
                                   prowlarr_url="http://prowlarr:9696")
    assert not post.called
    assert field(body(put), "baseUrl") == "http://radarr:7878" and field(body(put), "apiKey") == "NEWKEY"


async def test_health_untranslated_key_uses_wiki_sentence(mock):
    # Seen on a real Radarr 6: messages arrive as localization keys.
    mock.get(f"{RADARR}/api/v3/health").respond(json=[{
        "source": "IndexerRssCheck", "type": "error", "message": "IndexerRssHealthCheckNoIndexers",
        "wikiUrl": "https://wiki.servarr.com/radarr/system#no-indexers-available-with-rss-sync-enabled"}])
    async with radarr() as a:
        issues = await a.health_issues()
    assert issues[0].message == "No indexers available with rss sync enabled"
    assert issues[0].explanation  # beginner explanation still attached


# ---------------------------------------------------------------- quality definitions / custom formats / profiles


async def test_ensure_quality_definitions_updates_only_changed(mock):
    existing = [
        {"id": 1, "quality": {"id": 7, "name": "Bluray-1080p"}, "title": "Bluray-1080p",
         "minSize": 10.0, "maxSize": 100.0, "preferredSize": 95.0},
        {"id": 2, "quality": {"id": 3, "name": "WEBDL-1080p"}, "title": "WEBDL-1080p",
         "minSize": 12.5, "maxSize": 2000.0, "preferredSize": 1999.0},
    ]
    mock.get(f"{RADARR}/api/v3/qualitydefinition").respond(json=existing)
    put_1 = mock.put(f"{RADARR}/api/v3/qualitydefinition/1").respond(json=existing[0])
    put_2 = mock.put(f"{RADARR}/api/v3/qualitydefinition/2").respond(json=existing[1])
    async with radarr() as a:
        res = await a.ensure_quality_definitions([
            {"quality": "Bluray-1080p", "min": 50.8, "preferred": 1999.0, "max": 2000.0},
            {"quality": "WEBDL-1080p", "min": 12.5, "preferred": 1999.0, "max": 2000.0},
        ])
    assert res == {"updated": ["Bluray-1080p"], "unchanged": ["WEBDL-1080p"]}
    assert put_1.called and not put_2.called
    assert body(put_1)["minSize"] == 50.8 and body(put_1)["maxSize"] == 2000.0


async def test_ensure_custom_format_create_unchanged_and_update(mock):
    cf_trash = {
        "trash_id": "ed38b889b31be83fda192888e2286d83",
        "name": "BR-DISK",
        "includeCustomFormatWhenRenaming": False,
        "specifications": [{
            "name": "BR-DISK",
            "implementation": "ReleaseTitleSpecification",
            "negate": False,
            "required": True,
            "fields": {"value": "BR-DISK"},
        }],
    }
    mock.get(f"{RADARR}/api/v3/customformat").respond(json=[])
    post = mock.post(f"{RADARR}/api/v3/customformat").respond(json={
        "id": 10,
        "name": "BR-DISK",
        "includeCustomFormatWhenRenaming": False,
        "specifications": [{
            "name": "BR-DISK",
            "implementation": "ReleaseTitleSpecification",
            "negate": False,
            "required": True,
            "fields": [{"name": "value", "value": "BR-DISK", "order": 0}],
        }],
    })
    put = mock.put(f"{RADARR}/api/v3/customformat/10").respond(json={"id": 10, "name": "BR-DISK"})

    async with radarr() as a:
        created, action1 = await a.ensure_custom_format(cf_trash)
        assert action1 == "created" and created["id"] == 10
        assert body(post)["specifications"][0]["fields"] == [{"name": "value", "value": "BR-DISK"}]
        assert "trash_id" not in body(post)

        # Second call with identical spec is a no-op
        same, action2 = await a.ensure_custom_format(cf_trash, existing=[created])
        assert action2 == "unchanged" and same["id"] == 10 and not put.called

        # Modified regex triggers PUT
        changed_cf = {**cf_trash, "includeCustomFormatWhenRenaming": True}
        _, action3 = await a.ensure_custom_format(changed_cf, existing=[created])
        assert action3 == "updated" and put.called and body(put)["includeCustomFormatWhenRenaming"] is True


async def test_ensure_quality_profile_preserves_user_profiles(mock):
    user_prof = {
        "id": 1, "name": "My Custom Profile", "upgradeAllowed": True, "cutoff": 7, "items": [], "formatItems": [],
    }
    trash_prof = {
        "name": "HD Bluray + WEB",
        "upgradeAllowed": True,
        "cutoff": 7,
        "minFormatScore": 0,
        "cutoffFormatScore": 10000,
        "minUpgradeFormatScore": 1,
        "items": [{"quality": {"id": 7, "name": "Bluray-1080p"}, "items": [], "allowed": True}],
        "formatItems": [{"format": 10, "name": "BR-DISK", "score": -10000}],
    }
    mock.get(f"{RADARR}/api/v3/qualityprofile").respond(json=[user_prof])
    post = mock.post(f"{RADARR}/api/v3/qualityprofile").respond(json={**trash_prof, "id": 2})
    put = mock.put(f"{RADARR}/api/v3/qualityprofile/2").respond(json={**trash_prof, "id": 2, "minFormatScore": 10})
    dele = mock.delete(url__regex=r".*/qualityprofile.*")

    async with radarr() as a:
        created, act1 = await a.ensure_quality_profile(trash_prof)
        assert act1 == "created" and created["id"] == 2 and post.called and not dele.called

        _, act2 = await a.ensure_quality_profile(trash_prof, existing=[user_prof, created])
        assert act2 == "unchanged" and not put.called

        _, act3 = await a.ensure_quality_profile({**trash_prof, "minFormatScore": 10}, existing=[user_prof, created])
        assert act3 == "updated" and put.called and not dele.called
