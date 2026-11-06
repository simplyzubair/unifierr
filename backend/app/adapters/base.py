"""Shared contract for every integration adapter.

An adapter wraps ONE external app's HTTP API and returns the normalized models below.
Adapters never touch the database; they receive a ready `Connection` (decrypted secrets).
All network errors are converted to `ServiceUnavailable` with a plain-English explanation.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar, Literal

import httpx
from pydantic import BaseModel, Field

from app.core.errors import ServiceUnavailable


class ServiceKind(StrEnum):
    radarr = "radarr"
    sonarr = "sonarr"
    prowlarr = "prowlarr"
    qbittorrent = "qbittorrent"
    bazarr = "bazarr"
    jellyfin = "jellyfin"
    plex = "plex"


@dataclass(slots=True)
class Connection:
    kind: ServiceKind
    base_url: str  # e.g. http://radarr:7878 (no trailing slash)
    api_key: str | None = None  # *arr/Bazarr API key, Jellyfin API key, Plex token
    username: str | None = None  # qBittorrent
    password: str | None = None  # qBittorrent
    timeout: float = 15.0


# ---------- normalized models (shared with the REST API / frontend) ----------

Severity = Literal["info", "warning", "error"]


class HealthIssue(BaseModel):
    severity: Severity
    message: str  # short, e.g. "Indexers are unavailable"
    explanation: str | None = None  # plain English: what this means for the user
    fix: str | None = None  # plain English: what to do about it
    source: str | None = None  # app reporting it


class HealthStatus(BaseModel):
    ok: bool
    version: str | None = None
    message: str  # e.g. "Connected" / "Wrong API key"
    issues: list[HealthIssue] = Field(default_factory=list)


MediaType = Literal["movie", "series"]


class MediaItem(BaseModel):
    media_type: MediaType
    title: str
    year: int | None = None
    overview: str | None = None
    poster_url: str | None = None  # absolute https URL (remote image), never an internal URL
    tmdb_id: int | None = None
    tvdb_id: int | None = None
    imdb_id: str | None = None
    external_id: int | None = None  # Radarr movie id / Sonarr series id when already in library
    in_library: bool = False  # already added to Radarr/Sonarr
    monitored: bool = False
    has_file: bool = False  # movie: file present; series: any episode file present
    percent_complete: float | None = None  # series: episodeFileCount / episodeCount * 100
    size_on_disk: int | None = None
    status: str | None = None  # e.g. "released", "continuing", "ended"


class QueueItem(BaseModel):
    """One download, merged from qBittorrent and/or Radarr/Sonarr queues."""
    id: str  # torrent hash (lowercase) when known, otherwise "<source>:<queue id>"
    name: str
    source: Literal["qbittorrent", "radarr", "sonarr"]
    state: Literal["downloading", "seeding", "paused", "queued", "stalled", "checking", "completed",
                   "importing", "error", "unknown"]
    progress: float  # 0..100
    size: int | None = None  # bytes
    downloaded: int | None = None
    download_speed: int | None = None  # bytes/s
    upload_speed: int | None = None
    eta_seconds: int | None = None
    category: str | None = None
    save_path: str | None = None
    media_title: str | None = None  # from the *arr queue
    media_type: MediaType | None = None
    error: str | None = None  # plain-English problem, if any


class Indexer(BaseModel):
    id: int
    name: str
    protocol: str  # torrent | usenet
    enabled: bool
    privacy: str | None = None  # public | private | semiPrivate
    implementation: str | None = None
    status: str | None = None  # e.g. "ok", "disabled until 12:00 (too many failures)"


class IndexerSchema(BaseModel):
    """A template from Prowlarr's catalogue that can be added with few/no fields."""
    name: str  # definition name, e.g. "1337x"
    implementation: str
    protocol: str
    privacy: str | None = None
    description: str | None = None
    language: str | None = None
    required_fields: list[dict[str, Any]] = Field(default_factory=list)  # [{name,label,type,value}]


class LibraryInfo(BaseModel):
    id: str
    name: str
    type: str  # movies | tvshows | ...
    paths: list[str] = Field(default_factory=list)


class DiskSpace(BaseModel):
    path: str
    label: str | None = None
    free_bytes: int
    total_bytes: int


class SubtitleWanted(BaseModel):
    media_type: MediaType
    title: str
    episode: str | None = None  # "S01E02 - Title" for series
    missing_languages: list[str]
    external_id: int  # Bazarr's radarrId / sonarrEpisodeId


# ---------- adapter base ----------


class BaseAdapter(ABC):
    kind: ClassVar[ServiceKind]
    display_name: ClassVar[str]
    default_port: ClassVar[int]

    def __init__(self, conn: Connection, client: httpx.AsyncClient | None = None):
        self.conn = conn
        self._own_client = client is None
        self.client = client or httpx.AsyncClient(timeout=conn.timeout, follow_redirects=False)

    async def aclose(self) -> None:
        if self._own_client:
            await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()

    @abstractmethod
    async def ping(self) -> HealthStatus:
        """Check reachability + credentials. Must NOT raise for connection problems;
        return HealthStatus(ok=False, message=..., issues=[...]) instead."""

    async def health_issues(self) -> list[HealthIssue]:
        """App-reported problems (e.g. *arr /health), translated to plain English. Default: none."""
        return []

    # ---- helpers for subclasses ----
    def _url(self, path: str) -> str:
        return self.conn.base_url.rstrip("/") + path

    async def _request(self, method: str, path: str, **kw) -> httpx.Response:
        """Perform a request and map failures to ServiceUnavailable with explanations."""
        name = self.display_name
        try:
            resp = await self.client.request(method, self._url(path), **kw)
        except httpx.ConnectError as exc:
            raise ServiceUnavailable(
                f"Cannot reach {name}",
                explanation=f"Unifierr could not open a connection to {name} at {self.conn.base_url}.",
                fix=f"Make sure {name} is running and that the address is correct.",
            ) from exc
        except httpx.TimeoutException as exc:
            raise ServiceUnavailable(
                f"{name} did not answer in time",
                explanation=f"{name} is reachable but too slow or stuck.",
                fix=f"Restart {name}. If it keeps happening, check its logs.",
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailable(f"Error talking to {name}: {exc.__class__.__name__}") from exc
        if resp.status_code in (401, 403):
            raise ServiceUnavailable(
                f"{name} rejected the credentials",
                explanation=f"{name} answered, but the API key or password is wrong.",
                fix="Re-run detection in Settings → Apps so Unifierr can read the key again, or paste it manually.",
            )
        if resp.status_code >= 400:
            detail = _error_detail(resp)
            if resp.status_code >= 500:
                raise ServiceUnavailable(
                    f"{name} had an internal problem ({resp.status_code})",
                    explanation=detail or f"{name} could not finish this request. Often a folder path it "
                                          "cannot see, or a setting it does not accept.",
                    fix=f"Open {name}'s logs (Settings → Apps → {name} → View logs) for the exact reason, then Retry.",
                )
            raise ServiceUnavailable(
                f"{name} refused the request ({resp.status_code})",
                explanation=detail or None,
            )
        return resp


def _error_detail(resp: httpx.Response) -> str | None:
    """Turn an app's error body into one readable line (the *arr apps return validation lists)."""
    try:
        data = resp.json()
    except ValueError:
        text = resp.text.strip()
        return text[:300] if text and not text.lstrip().startswith("<") else None
    if isinstance(data, list):
        msgs = [str(d.get("errorMessage") or d.get("message")) for d in data if isinstance(d, dict)
                and (d.get("errorMessage") or d.get("message"))]
        return "; ".join(msgs)[:300] or None
    if isinstance(data, dict):
        msg = data.get("message") or data.get("error") or data.get("detail") or data.get("title")
        return str(msg)[:300] if msg else None
    return None
