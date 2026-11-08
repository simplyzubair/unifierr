# Unifierr — shared contracts (owner: lead architect)

These interfaces are the agreements between workstreams. **Do not change a signature
here without the lead's approval.** You may ADD optional parameters / extra methods.

Repository layout:

```
backend/app/core/        config, db, crypto, security, errors, logging    (lead)
backend/app/models/      SQLAlchemy tables                                (lead)
backend/app/adapters/    one module per external app                      (integration workstream)
backend/app/deploy/      Docker, environment detection, folders, keys     (deployment workstream)
backend/app/services/    orchestration: wiring, requests, health           (lead)
backend/app/api/         FastAPI routers                                   (lead)
backend/tests/           pytest (respx for HTTP mocks — tests only)
frontend/                Vite + React + TypeScript SPA                     (frontend workstream)
deploy/                  Dockerfile, docker-compose.yml, examples          (deployment workstream)
docs/                    user + developer docs
```

Stack decision: **one container**. FastAPI serves the API under `/api` and the built SPA
(static files) at `/`. No Node.js at runtime. SQLite in `/config` (single household app;
Postgres possible later through `UNIFIERR_DATABASE_URL`). Vite+React instead of Next.js because
the UI is a private, authenticated SPA: no SSR/SEO benefit, and a static build keeps the image
small and the deployment one container.

---

## 1. Adapters (`backend/app/adapters/`)

Base classes and normalized models live in `adapters/base.py` (read it first). Each adapter:

* subclasses `BaseAdapter`, sets `kind`, `display_name`, `default_port`;
* uses `self._request(...)` for all HTTP calls (gives friendly errors);
* returns only the normalized pydantic models from `base.py` or plain dict/list where stated;
* `ping()` never raises for network/auth problems.

`adapters/__init__.py` must export `get_adapter(conn: Connection, client=None) -> BaseAdapter`
(registry by `ServiceKind`).

### RadarrAdapter (`radarr.py`, API v3, header `X-Api-Key`)
```
ping() -> HealthStatus                         # GET /api/v3/system/status
health_issues() -> list[HealthIssue]           # GET /api/v3/health, translated to plain English
lookup(term: str) -> list[MediaItem]           # GET /api/v3/movie/lookup?term=
list_movies() -> list[MediaItem]               # GET /api/v3/movie
add_movie(tmdb_id: int, *, root_folder: str | None = None, quality_profile_id: int | None = None,
          search: bool = True) -> MediaItem    # lookup/tmdb then POST /api/v3/movie; defaults: first root folder, first profile
delete_movie(movie_id: int, delete_files: bool = False) -> None
queue() -> list[QueueItem]                     # GET /api/v3/queue?includeMovie=true&pageSize=200
quality_profiles() -> list[dict]               # [{id,name,...}]
create_quality_profile(profile: dict) -> dict  # POST /api/v3/qualityprofile
update_quality_profile(id: int, profile: dict) -> dict
ensure_quality_profile(profile: dict) -> tuple[dict, str]  # idempotent by name; never deletes user profiles
custom_formats() -> list[dict]                 # GET /api/v3/customformat
create_custom_format(cf: dict) -> dict         # POST /api/v3/customformat
update_custom_format(id: int, cf: dict) -> dict
ensure_custom_format(cf: dict) -> tuple[dict, str]         # idempotent by name
quality_definitions() -> list[dict]            # GET /api/v3/qualitydefinition
update_quality_definition(id: int, defn: dict) -> dict
ensure_quality_definitions(defns: list[dict]) -> dict      # idempotent min/preferred/max size update
root_folders() -> list[dict]                   # [{id,path,freeSpace,accessible}]
ensure_root_folder(path: str) -> dict          # idempotent
ensure_qbittorrent_client(*, host: str, port: int, username: str, password: str,
                          category: str = "radarr") -> dict   # idempotent, by implementation+host
ensure_media_server_notification(*, kind: "jellyfin"|"plex", host: str, port: int,
                                 api_key: str, use_ssl: bool = False) -> dict
                                               # Jellyfin -> implementation "MediaBrowser"; Plex -> "PlexServer"
disk_space() -> list[DiskSpace]                # GET /api/v3/diskspace
api_key_valid() -> bool
```

### SonarrAdapter (`sonarr.py`, API v3) — same shape as Radarr with series:
```
ping, health_issues, lookup(term), list_series(), add_series(tvdb_id, *, root_folder=None,
quality_profile_id=None, search=True, monitor="all") , delete_series(series_id, delete_files=False),
queue(), quality_profiles(), root_folders(), ensure_root_folder(path),
ensure_qbittorrent_client(..., category="tv-sonarr"), ensure_media_server_notification(...), disk_space()
```
Sonarr v4: `languageProfileId` is gone; send it only if `/api/v3/languageprofile` exists (v3).

### ProwlarrAdapter (`prowlarr.py`, API v1)
```
ping, health_issues
indexers() -> list[Indexer]
indexer_schemas() -> list[IndexerSchema]       # GET /api/v1/indexer/schema
add_indexer(definition_name: str, fields: dict[str, Any] | None = None) -> Indexer
delete_indexer(indexer_id: int) -> None
set_indexer_enabled(indexer_id: int, enabled: bool) -> Indexer
test_all_indexers() -> list[dict]              # POST /api/v1/indexer/testall -> [{id,isValid,errors:[str]}]
ensure_application(*, kind: "radarr"|"sonarr", app_url: str, app_api_key: str,
                   prowlarr_url: str) -> dict  # POST /api/v1/applications, syncLevel fullSync, idempotent
ensure_flaresolverr(...)  # NOT in v1 — leave out
```

### QbittorrentAdapter (`qbittorrent.py`, WebUI API v2, cookie login)
```
ping()                                         # POST /api/v2/auth/login then GET /api/v2/app/version
torrents() -> list[QueueItem]                  # GET /api/v2/torrents/info
pause(hashes: list[str]), resume(hashes: list[str])   # handle v5 rename stop/start (try new, fall back)
delete(hashes: list[str], delete_files: bool = False)
ensure_category(name: str, save_path: str) -> None
set_preferences(prefs: dict) -> None           # POST /api/v2/app/setPreferences json=...
transfer_info() -> dict                        # {dl_speed, up_speed}
```
Login: form `username`/`password`, `Referer`/`Origin` header = base_url (qBit CSRF check).
"Fails." body means bad credentials -> ServiceUnavailable with clear text. Re-login once on 403.

### BazarrAdapter (`bazarr.py`, header `X-API-KEY`)
```
ping()                                         # GET /api/system/status
health_issues()                                # GET /api/system/health
wanted() -> list[SubtitleWanted]               # /api/movies/wanted + /api/episodes/wanted (length=100)
search_all_missing() -> None                   # POST /api/system/tasks?taskid=wanted_search_missing_subtitles_movies and _series
ensure_arr_connection(*, kind: "radarr"|"sonarr", host: str, port: int, api_key: str) -> None
                                               # POST /api/system/settings (form data settings-radarr-*/settings-sonarr-*, settings-general-use_radarr=true)
ensure_default_language_profile(languages: list[str] = ["en"]) -> None   # best effort
```

### JellyfinAdapter (`jellyfin.py`, header `Authorization: MediaBrowser Token="..."`)
```
ping()                                         # GET /System/Info (auth) ; /System/Info/Public for version when no key
startup_needed() -> bool                       # GET /Startup/Configuration returns 200 only before wizard done (or /System/Info/Public StartupWizardCompleted)
run_startup_wizard(admin_user: str, admin_password: str, *, ui_culture="en-US",
                   metadata_country="US", metadata_language="en") -> None
authenticate(username: str, password: str) -> str   # POST /Users/AuthenticateByName -> AccessToken
create_api_key(app_name: str = "Unifierr") -> str   # POST /Auth/Keys?App=..., then GET /Auth/Keys to read it
libraries() -> list[LibraryInfo]               # GET /Library/VirtualFolders
ensure_library(name: str, collection_type: "movies"|"tvshows", path: str) -> LibraryInfo
refresh_library() -> None                      # POST /Library/Refresh
recently_added(limit: int = 20) -> list[MediaItem]   # best effort, poster_url may be None
```

### PlexAdapter (`plex.py`, header `X-Plex-Token`, `Accept: application/json`)
```
ping()                                         # GET /identity (no auth) + GET / with token
libraries() -> list[LibraryInfo]               # GET /library/sections
ensure_library(name, collection_type: "movies"|"tvshows", path) -> LibraryInfo
                                               # POST /library/sections?name&type=movie|show&agent&scanner&language&location
refresh_library() -> None                      # GET /library/sections/all/refresh
recently_added(limit=20) -> list[MediaItem]
```

---

## 2. Deployment engine (`backend/app/deploy/`)

Design rule: Unifierr's container mounts the Docker socket and the **storage root at the same
path inside and outside** (`/srv/unifierr:/srv/unifierr` by default, configured by
`UNIFIERR_ROOT`). Then paths Unifierr creates and passes to other containers are identical on the
host. Managed containers join a Docker network `unifierr` and are reached by container name.

Folder layout (TRaSH-guides style, one filesystem so hardlinks work):
```
<root>/appdata/<app>/          per-app config (mounted to /config)
<root>/data/torrents/{movies,tv}
<root>/data/media/{movies,tv}
```
Every app gets `/data` = `<root>/data` so paths match between qBittorrent, Radarr, Sonarr, Jellyfin.

Modules and required functions:

```python
# deploy/environment.py
class EnvironmentReport(BaseModel):
    platform: Literal["synology","unraid","truenas","linux","windows","macos","unknown"]
    in_container: bool
    docker_available: bool
    docker_version: str | None
    docker_error: str | None          # plain English why not available + fix
    suggested_root: str               # e.g. /volume1/docker/unifierr on Synology, /mnt/user/... on Unraid
    puid: int; pgid: int; timezone: str
    notes: list[str]                  # platform-specific tips (plain English)
def detect_environment(docker: "DockerManager") -> EnvironmentReport

# deploy/catalog.py
class AppSpec(BaseModel):
    kind: ServiceKind; display_name: str; image: str; container_name: str
    internal_port: int; default_host_port: int
    volumes: dict[str, str]           # host template -> container path; templates use {root},{appdata}
    env: dict[str, str]               # may use {puid},{pgid},{tz}
    healthcheck_path: str             # HTTP path that returns 200 when up
    description: str                  # one beginner-friendly sentence
CATALOG: dict[ServiceKind, AppSpec]   # radarr, sonarr, prowlarr, qbittorrent, bazarr, jellyfin (lscr.io/linuxserver/* images; plex optional)

# deploy/docker_manager.py
class ContainerInfo(BaseModel):
    id: str; name: str; image: str; status: str   # running|exited|...
    health: str | None; ports: dict[int, int | None]  # container port -> host port
    networks: list[str]; mounts: list[dict]         # [{source,destination}]
    labels: dict[str, str]
class DockerManager:
    def __init__(self, docker_host: str | None = None)   # lazy connect; never raises at init
    available() -> bool ; error() -> str | None
    list_containers(all: bool = True) -> list[ContainerInfo]
    ensure_network(name: str = "unifierr") -> None
    connect_network(container: str, network: str = "unifierr") -> None   # non-destructive
    install(spec: AppSpec, *, root: str, puid: int, pgid: int, tz: str, host_port: int | None = None,
            progress: Callable[[str], None] | None = None) -> ContainerInfo
        # pull image (report progress), create with restart unless-stopped, labels
        # {"io.unifierr.managed": "true", "io.unifierr.kind": kind}, network unifierr. Refuse if a
        # container with that name exists (raise UnifierrError with explanation).
    start/stop/restart(name) -> None
    update(name, progress=None) -> ContainerInfo   # pull newer image; recreate with SAME config/mounts/env/ports/networks; only for managed containers
    logs(name, tail: int = 200) -> str
    self_container() -> ContainerInfo | None       # Unifierr's own container (by hostname/cgroup)
# All blocking docker-py calls; the API layer runs them in a threadpool.

# deploy/detect.py
class DetectedApp(BaseModel):
    kind: ServiceKind; source: Literal["docker","network"]
    container_name: str | None; image: str | None
    url_candidates: list[str]         # ordered: best first (container name on shared network, host ip:port)
    reachable_url: str | None         # first candidate that answered
    config_path: str | None           # host path of /config mount, when readable
    api_key_found: bool
    managed: bool
def detect_apps(docker: DockerManager, *, probe_hosts: list[str] | None = None) -> list[DetectedApp]
    # (async allowed) match images by name (linuxserver/radarr, hotio/radarr, ghcr.io/..., jellyfin/jellyfin, plexinc/pms-docker ...)
    # and probe default ports on probe_hosts (host.docker.internal, gateway ip, localhost)

# deploy/keys.py  (read credentials so users never copy API keys)
read_arr_api_key(config_dir: str) -> str | None        # config.xml <ApiKey>  (radarr/sonarr/prowlarr)
read_bazarr_api_key(config_dir: str) -> str | None     # config/config.yaml auth.apikey (or config.ini [auth] apikey)
preseed_qbittorrent(config_dir: str, username: str, password: str) -> None
    # write qBittorrent/qBittorrent.conf with WebUI\Username and WebUI\Password_PBKDF2 = "@ByteArray(salt:hash)"
    # (PBKDF2-HMAC-SHA512, 100000 iterations, 16-byte salt, base64) + downloads path /data/torrents,
    # only if the file does not exist yet (never overwrite an existing install)
preseed_arr_config(config_dir: str, api_key: str, port: int) -> None   # write minimal config.xml only if absent
generate_api_key() -> str                               # 32 hex chars

# deploy/folders.py
class FolderReport(BaseModel):
    root: str; created: list[str]; existing: list[str]
    writable: bool; same_filesystem: bool   # hardlinks possible between torrents and media
    free_bytes: int; total_bytes: int
    problems: list[HealthIssue]
prepare_folders(root: str, puid: int, pgid: int) -> FolderReport   # create layout, chown only dirs it created
check_folders(root: str) -> FolderReport                            # read-only check
```

---

## 3. REST API (`/api`, JSON) — what the frontend uses

Auth: cookie `unifierr_session` (httpOnly). **Every POST/PUT/PATCH/DELETE must send header
`X-Unifierr-CSRF: 1`.** Errors: `{"detail": "..."}` (FastAPI) or
`{"error","explanation","fix"}` (Unifierr errors). 401 → show login. Times are ISO-8601 UTC.

### Auth & users
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | /api/health | – | `{status:"ok", version}` (no auth) |
| GET | /api/setup/status | – | `{has_admin, setup_complete, docker_available, version}` (no auth) |
| POST | /api/auth/bootstrap | `{username,password}` | user; only when no users exist; logs in |
| POST | /api/auth/login | `{username,password}` | user |
| POST | /api/auth/logout | – | 204 |
| GET | /api/auth/me | – | `{id,username,role}` |
| POST | /api/auth/password | `{current_password,new_password}` | 204 |
| GET/POST | /api/users | `{username,password,role}` | admin only |
| DELETE | /api/users/{id} | – | admin only |

### Setup wizard (admin)
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | /api/setup/environment | – | EnvironmentReport |
| GET | /api/setup/detect | – | `DetectedApp[]` |
| POST | /api/setup/folders | `{root,puid,pgid,timezone}` | FolderReport (saves settings) |
| POST | /api/setup/install | `{kinds: ServiceKind[]}` | `{job_id}` |
| GET | /api/jobs/{id} | – | Job `{id,kind,status:"running"|"done"|"failed",steps:[{name,status,message}],log:[str],result}` |
| POST | /api/setup/adopt | `{kind, base_url?, api_key?, username?, password?}` | Service (tests connection first; reads key from config when omitted & detected) |
| POST | /api/setup/wire | – | `{job_id}` — auto-integration (see §4) |
| GET | /api/setup/trash (or /api/trash/status) | – | TrashStatus (chosen_profile, available_profiles, last_sync, apps) |
| POST | /api/setup/trash (or /api/trash/apply) | `{profile?, kinds?}` | `{job_id, profile}` — sync TRaSH profiles & custom formats |
| POST | /api/setup/complete | – | status |

### Services (admin)
`GET /api/services` → `ServiceOut[]` `{id,kind,name,base_url,managed,container_name,enabled,has_api_key,status:HealthStatus}`
`POST /api/services/{id}/test`, `PATCH /api/services/{id}` `{base_url?,api_key?,username?,password?,enabled?}`,
`DELETE /api/services/{id}` (forget only; never deletes containers or data),
`POST /api/services/{id}/restart`, `POST /api/services/{id}/update` → `{job_id}`, `GET /api/services/{id}/logs?tail=200` → `{logs}`.
`ServiceOut` also has `has_login: bool`. `GET /api/services/{id}/credentials` → `{username, password}` (the login
Unifierr created for Jellyfin/qBittorrent; shown behind a "Show login" button; access is logged).
`GET /api/settings` also returns `{language, media_server, setup_complete, version}`; `PUT /api/settings` accepts
`{timezone?, language?, puid?, pgid?}`.

### Media & requests (any signed-in user)
`GET /api/media/search?q=&type=movie|series|all` → `MediaResult[]` = MediaItem + `{request: RequestOut|null, availability: "available"|"downloading"|"requested"|"missing"|"not_added"}`
`GET /api/media/library?type=movie|series` → MediaResult[]
`GET /api/media/recent` → MediaItem[] (Jellyfin/Plex recently added)
`GET /api/requests?status=` → RequestOut[] `{id,media_type,tmdb_id,tvdb_id,title,year,poster_url,status,availability,requested_by,created_at,note}` (users see their own; admin sees all)
`POST /api/requests` `{media_type,tmdb_id?,tvdb_id?,title,year?,poster_url?}` → RequestOut (admin's requests are auto-approved and added)
`POST /api/requests/{id}/approve` | `/deny` `{note?}` (admin), `DELETE /api/requests/{id}` (owner/admin)

### Downloads, indexers, subtitles, storage, health (admin)
`GET /api/downloads` → `{items: QueueItem[], dl_speed, up_speed}`; `POST /api/downloads/{id}/pause|resume`; `DELETE /api/downloads/{id}?delete_files=false`
`GET /api/indexers` → Indexer[]; `GET /api/indexers/schemas` → IndexerSchema[]; `POST /api/indexers` `{definition_name, fields?}`; `DELETE /api/indexers/{id}`; `PATCH /api/indexers/{id}` `{enabled}`; `POST /api/indexers/test` → results
`GET /api/subtitles/wanted` → SubtitleWanted[]; `POST /api/subtitles/search` → 202
`GET /api/storage` → `{folders: FolderReport|null, disks: DiskSpace[]}`
`GET /api/health/overview` → `{overall:"ok"|"warning"|"error", services:[{kind,name,status:HealthStatus}], issues: HealthIssue[]}`
`GET /api/events?limit=100` → Event[] `{id,ts,level,source,message}`
`GET /api/system/backup` → zip download (db + secret.key + settings); `POST /api/system/restore` multipart file (admin)
`GET /api/settings` / `PUT /api/settings` → `{root,puid,pgid,timezone,movies_path,tv_path,downloads_path,language}`

---

## 4. Auto-wiring (services/wiring.py, lead) — order of steps
1. Ensure root folders `/data/media/movies` in Radarr and `/data/media/tv` in Sonarr.
2. Add qBittorrent as download client in Radarr (category `radarr`) and Sonarr (`tv-sonarr`); create those categories in qBittorrent with save paths `/data/torrents/movies|tv`.
3. Add Radarr + Sonarr as applications in Prowlarr (full sync) so indexers flow to both.
4. Connect Bazarr to Radarr + Sonarr.
5. Jellyfin: run startup wizard if needed, create API key, ensure libraries Movies=`/data/media/movies`, Shows=`/data/media/tv`; or Plex: ensure libraries.
6. Add Jellyfin/Plex notification to Radarr + Sonarr so new imports appear immediately.
Each step is idempotent and reports `ok | skipped (reason) | failed (explanation, fix)`.
