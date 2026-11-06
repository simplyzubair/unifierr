"""Plex Media Server adapter. The Plex token comes from `Connection.api_key`."""
from __future__ import annotations

from typing import Any, ClassVar

import httpx

from app.adapters._arr_common import failed_status, norm_path, parse_json
from app.adapters.base import (
    BaseAdapter,
    HealthStatus,
    LibraryInfo,
    MediaItem,
    ServiceKind,
)
from app.core.errors import ServiceUnavailable

# Unifierr collection type -> (Plex section type, agent, scanner)
_TYPES: dict[str, tuple[str, str, str]] = {
    "movies": ("movie", "tv.plex.agents.movie", "Plex Movie"),
    "tvshows": ("show", "tv.plex.agents.series", "Plex TV Series"),
}
_PLEX_TO_OURS = {"movie": "movies", "show": "tvshows"}


class PlexAdapter(BaseAdapter):
    kind: ClassVar[ServiceKind] = ServiceKind.plex
    display_name: ClassVar[str] = "Plex"
    default_port: ClassVar[int] = 32400

    def _plex_headers(self) -> dict[str, str]:
        h = {"Accept": "application/json", "X-Plex-Client-Identifier": "unifierr",
             "X-Plex-Product": "Unifierr", "X-Plex-Version": "0.1.0"}
        if self.conn.api_key:
            h["X-Plex-Token"] = self.conn.api_key
        return h

    async def _api(self, method: str, path: str, **kw: Any) -> httpx.Response:
        headers = {**self._plex_headers(), **kw.pop("headers", {})}
        return await self._request(method, path, headers=headers, **kw)

    async def _container(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        resp = await self._api(method, path, **kw)
        if not resp.content:
            return {}
        data = parse_json(resp, self.display_name)
        return data.get("MediaContainer", {}) if isinstance(data, dict) else {}

    async def ping(self) -> HealthStatus:
        try:
            ident = await self._container("GET", "/identity")  # needs no token: proves the server is up
            version = ident.get("version")
            if not self.conn.api_key:
                return HealthStatus(ok=True, version=version, message="Connected (no Plex token yet)")
            await self._api("GET", "/")  # needs a valid token
        except ServiceUnavailable as exc:
            return failed_status(exc, "plex")
        return HealthStatus(ok=True, version=version, message="Connected")

    # ---- libraries ----
    @staticmethod
    def _lib(d: dict[str, Any]) -> LibraryInfo:
        locs = d.get("Location") or []
        if isinstance(locs, dict):
            locs = [locs]
        ptype = str(d.get("type") or "")
        return LibraryInfo(id=str(d.get("key", "")), name=str(d.get("title") or ""),
                           type=_PLEX_TO_OURS.get(ptype, ptype),
                           paths=[str(loc.get("path")) for loc in locs if loc.get("path")])

    async def _sections(self) -> list[dict[str, Any]]:
        return (await self._container("GET", "/library/sections")).get("Directory") or []

    async def libraries(self) -> list[LibraryInfo]:
        return [self._lib(d) for d in await self._sections()]

    async def ensure_library(self, name: str, collection_type: str, path: str | list[str]) -> LibraryInfo:
        if collection_type not in _TYPES:
            raise ServiceUnavailable(
                f"Unsupported Plex library type: {collection_type}",
                explanation=f"Unifierr cannot create a '{collection_type}' library in Plex.",
                fix="Use 'movies' or 'tvshows'.")
        paths = [path] if isinstance(path, str) else list(path)
        wanted = {norm_path(p) for p in paths}
        for d in await self._sections():
            lib = self._lib(d)
            if wanted & {norm_path(p) for p in lib.paths}:
                return lib
        ptype, agent, scanner = _TYPES[collection_type]
        # Plex wants everything as query parameters, with one `location` per folder.
        params: dict[str, Any] = {"name": name, "type": ptype, "agent": agent, "scanner": scanner,
                                  "language": "en-US", "location": paths}
        created = await self._container("POST", "/library/sections", params=params)
        entries = created.get("Directory") or []
        if entries:
            return self._lib(entries[0])
        for d in await self._sections():
            if d.get("title") == name:
                return self._lib(d)
        return LibraryInfo(id="", name=name, type=collection_type, paths=paths)

    async def refresh_library(self) -> None:
        await self._api("GET", "/library/sections/all/refresh")

    async def recently_added(self, limit: int = 20) -> list[MediaItem]:
        cont = await self._container("GET", "/library/recentlyAdded", params={
            "X-Plex-Container-Start": "0", "X-Plex-Container-Size": str(limit)})
        out: list[MediaItem] = []
        seen: set[tuple[str, str]] = set()
        for m in cont.get("Metadata") or []:
            t = m.get("type")
            if t == "movie":
                mtype, title = "movie", m.get("title")
            elif t == "episode":
                mtype, title = "series", m.get("grandparentTitle") or m.get("title")
            elif t == "season":
                mtype, title = "series", m.get("parentTitle") or m.get("title")
            elif t == "show":
                mtype, title = "series", m.get("title")
            else:
                continue
            if not title or (mtype, title) in seen:
                continue
            seen.add((mtype, title))
            ids = {}
            for g in m.get("Guid") or []:
                scheme, _, value = str(g.get("id", "")).partition("://")
                ids[scheme] = value
            out.append(MediaItem(
                media_type=mtype, title=str(title), year=m.get("year"), overview=m.get("summary"),
                poster_url=None,  # Plex images need the token: never exposed as a URL
                tmdb_id=int(ids["tmdb"]) if ids.get("tmdb", "").isdigit() else None,
                tvdb_id=int(ids["tvdb"]) if ids.get("tvdb", "").isdigit() else None,
                imdb_id=ids.get("imdb") or None, in_library=True, has_file=True))
        return out
