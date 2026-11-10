"""Jellyfin 10.9 / 10.10 adapter."""
from __future__ import annotations

from typing import Any, ClassVar

import httpx

from app.adapters._arr_common import failed_status, norm_path, parse_json
from app.adapters.base import (
    BaseAdapter,
    HealthIssue,
    HealthStatus,
    LibraryInfo,
    MediaItem,
    ServiceKind,
)
from app.core.errors import ServiceUnavailable

_AUTH_BASE = 'MediaBrowser Client="Unifierr", Device="Unifierr", DeviceId="unifierr", Version="0.1.0"'


class JellyfinAdapter(BaseAdapter):
    kind: ClassVar[ServiceKind] = ServiceKind.jellyfin
    display_name: ClassVar[str] = "Jellyfin"
    default_port: ClassVar[int] = 8096

    # ---- helpers ----
    def _auth_headers(self, *, token: bool = True) -> dict[str, str]:
        value = _AUTH_BASE
        # Read the key at call time: wiring sets `conn.api_key` after logging in.
        if token and self.conn.api_key:
            value += f', Token="{self.conn.api_key}"'
        return {"Authorization": value, "Accept": "application/json"}

    async def _api(self, method: str, path: str, *, token: bool = True, **kw: Any) -> httpx.Response:
        headers = {**self._auth_headers(token=token), **kw.pop("headers", {})}
        return await self._request(method, path, headers=headers, **kw)

    # ---- BaseAdapter ----
    async def ping(self) -> HealthStatus:
        try:
            if self.conn.api_key:
                data = parse_json(await self._api("GET", "/System/Info"), self.display_name)
            else:  # no key yet (fresh install): the public endpoint still proves the server is up
                data = parse_json(await self._api("GET", "/System/Info/Public", token=False), self.display_name)
        except ServiceUnavailable as exc:
            return failed_status(exc, "jellyfin")
        version = data.get("Version") if isinstance(data, dict) else None
        msg = "Connected" if self.conn.api_key else "Connected (not signed in yet)"
        return HealthStatus(ok=True, version=version, message=msg)

    async def health_issues(self) -> list[HealthIssue]:
        info = parse_json(await self._api("GET", "/System/Info"), self.display_name)
        issues: list[HealthIssue] = []
        if info.get("HasPendingRestart"):
            issues.append(HealthIssue(
                severity="warning", message="Jellyfin needs a restart",
                explanation="A recent change only takes effect after Jellyfin restarts.",
                fix="Restart the Jellyfin container.", source="jellyfin"))
        if info.get("HasUpdateAvailable"):
            issues.append(HealthIssue(
                severity="info", message="A Jellyfin update is available",
                explanation="A newer Jellyfin version has been released.",
                fix="Update the container image (Unifierr → Apps → Update).", source="jellyfin"))
        return issues

    # ---- first-run wizard ----
    async def startup_needed(self) -> bool:
        data = parse_json(await self._api("GET", "/System/Info/Public", token=False), self.display_name)
        return data.get("StartupWizardCompleted") is False

    async def run_startup_wizard(self, admin_user: str, admin_password: str, *, ui_culture: str = "en-US",
                                 metadata_country: str = "US", metadata_language: str = "en") -> None:
        """Run Jellyfin's first-time setup. Unauthenticated by design: the wizard endpoints only work before setup."""
        kw: dict[str, Any] = {"token": False}
        await self._api("POST", "/Startup/Configuration", json={
            "UICulture": ui_culture, "MetadataCountryCode": metadata_country,
            "PreferredMetadataLanguage": metadata_language}, **kw)
        await self._api("GET", "/Startup/User", **kw)  # Jellyfin creates the default user on first read
        await self._api("POST", "/Startup/User", json={"Name": admin_user, "Password": admin_password}, **kw)
        await self._api("POST", "/Startup/RemoteAccess",
                        json={"EnableRemoteAccess": True, "EnableAutomaticPortMapping": False}, **kw)
        await self._api("POST", "/Startup/Complete", **kw)

    async def authenticate(self, username: str, password: str) -> str:
        resp = await self._api("POST", "/Users/AuthenticateByName", token=False,
                               json={"Username": username, "Pw": password})
        token = parse_json(resp, self.display_name).get("AccessToken")
        if not token:
            raise ServiceUnavailable("Jellyfin did not return a login token")
        return str(token)

    async def create_api_key(self, app_name: str = "Unifierr") -> str:
        await self._api("POST", "/Auth/Keys", params={"App": app_name})
        data = parse_json(await self._api("GET", "/Auth/Keys"), self.display_name)
        mine = [k for k in data.get("Items", []) if k.get("AppName") == app_name and k.get("AccessToken")]
        if not mine:
            raise ServiceUnavailable(
                "Jellyfin did not create an API key",
                explanation="The key was requested but is not in Jellyfin's key list.",
                fix="Make sure the Jellyfin account is an administrator, then try again.")
        return str(max(mine, key=lambda k: str(k.get("DateCreated", "")))["AccessToken"])

    async def played_movie_tmdb_ids(self) -> set[int]:
        users = parse_json(await self._api("GET", "/Users"), self.display_name)
        played: set[int] = set()
        for user in users or []:
            items = parse_json(await self._api("GET", "/Items", params={
                "userId": user["Id"], "Recursive": "true", "IncludeItemTypes": "Movie",
                "Filters": "IsPlayed", "Fields": "ProviderIds",
            }), self.display_name)
            for item in (items or {}).get("Items", []):
                value = (item.get("ProviderIds") or {}).get("Tmdb")
                try:
                    played.add(int(value))
                except (TypeError, ValueError):
                    continue
        return played

    # ---- libraries ----
    @staticmethod
    def _lib(d: dict[str, Any]) -> LibraryInfo:
        return LibraryInfo(id=str(d.get("ItemId") or d.get("Name") or ""), name=str(d.get("Name") or ""),
                           type=str(d.get("CollectionType") or "mixed"),
                           paths=[str(p) for p in d.get("Locations") or []])

    async def _folders(self) -> list[dict[str, Any]]:
        return parse_json(await self._api("GET", "/Library/VirtualFolders"), self.display_name) or []

    async def libraries(self) -> list[LibraryInfo]:
        return [self._lib(d) for d in await self._folders()]

    async def ensure_library(self, name: str, collection_type: str, path: str | list[str]) -> LibraryInfo:
        paths = [path] if isinstance(path, str) else list(path)
        wanted = {norm_path(p) for p in paths}
        folders = await self._folders()
        for d in folders:
            if wanted & {norm_path(str(p)) for p in d.get("Locations") or []}:
                return self._lib(d)
        same_name = next((d for d in folders if d.get("Name") == name), None)
        if same_name is not None:  # library exists but without this folder: add the folder to it
            for p in paths:
                await self._api("POST", "/Library/VirtualFolders/Paths",
                                params={"refreshLibrary": "true"}, json={"Name": name, "PathInfo": {"Path": p}})
        else:
            await self._api("POST", "/Library/VirtualFolders",
                            params={"name": name, "collectionType": collection_type, "refreshLibrary": "true",
                                    "paths": paths},
                            json={"LibraryOptions": {}})
        for d in await self._folders():
            if d.get("Name") == name:
                return self._lib(d)
        return LibraryInfo(id=name, name=name, type=collection_type, paths=paths)

    async def playing_file_names(self) -> set[str]:
        """Base names of the files anyone is streaming right now."""
        sessions = parse_json(await self._api("GET", "/Sessions"), self.display_name) or []
        paths = [(s.get("NowPlayingItem") or {}).get("Path") for s in sessions if isinstance(s, dict)]
        return {p.replace("\\", "/").rsplit("/", 1)[-1] for p in paths if p}

    async def refresh_library(self) -> None:
        await self._api("POST", "/Library/Refresh")

    async def recently_added(self, limit: int = 20) -> list[MediaItem]:
        data = parse_json(await self._api("GET", "/Items", params={
            "Recursive": "true", "SortBy": "DateCreated", "SortOrder": "Descending",
            "IncludeItemTypes": "Movie,Series", "Limit": str(limit),
            "Fields": "Overview,ProviderIds,ProductionYear"}), self.display_name)
        out: list[MediaItem] = []
        for it in data.get("Items", []):
            ids = it.get("ProviderIds") or {}
            tmdb, tvdb = ids.get("Tmdb"), ids.get("Tvdb")
            out.append(MediaItem(
                media_type="movie" if it.get("Type") == "Movie" else "series",
                title=str(it.get("Name") or "Unknown"), year=it.get("ProductionYear"),
                overview=it.get("Overview"), poster_url=None,  # Jellyfin images are internal URLs, never exposed
                tmdb_id=int(tmdb) if str(tmdb).isdigit() else None,
                tvdb_id=int(tvdb) if str(tvdb).isdigit() else None,
                imdb_id=ids.get("Imdb"), in_library=True, has_file=True))
        return out
