"""Sonarr v4 adapter (API v3; v3 compatible for the language profile)."""
from __future__ import annotations

from typing import Any, ClassVar

from app.adapters._arr_common import ArrAdapter, parse_json, poster_from_images
from app.adapters.base import MediaItem, ServiceKind
from app.core.errors import NotFound, ServiceUnavailable


def series_item(d: dict[str, Any]) -> MediaItem:
    """Map a Sonarr series / lookup resource to the normalized model."""
    sid = int(d.get("id") or 0)
    stats = d.get("statistics") or {}
    pct = stats.get("percentOfEpisodes")
    return MediaItem(
        media_type="series",
        title=str(d.get("title") or "Unknown"),
        year=d.get("year") or None,
        overview=d.get("overview") or None,
        poster_url=poster_from_images(d.get("images")),
        tmdb_id=d.get("tmdbId") or None,
        tvdb_id=d.get("tvdbId") or None,
        imdb_id=d.get("imdbId") or None,
        external_id=sid or None,
        in_library=sid > 0,
        monitored=bool(d.get("monitored", False)),
        has_file=int(stats.get("episodeFileCount") or 0) > 0,
        percent_complete=round(float(pct), 1) if pct is not None else None,
        size_on_disk=stats.get("sizeOnDisk") or None,
        status=d.get("status") or None,
    )


class SonarrAdapter(ArrAdapter):
    kind: ClassVar[ServiceKind] = ServiceKind.sonarr
    display_name: ClassVar[str] = "Sonarr"
    default_port: ClassVar[int] = 8989
    app_label: ClassVar[str] = "sonarr"
    qbit_category_field: ClassVar[str] = "tvCategory"
    queue_params: ClassVar[dict[str, str]] = {"includeSeries": "true", "includeEpisode": "true"}
    queue_media_type: ClassVar[str] = "series"
    queue_source: ClassVar[str] = "sonarr"
    queue_media_key: ClassVar[str] = "series"

    async def lookup(self, term: str) -> list[MediaItem]:
        data = await self._json("GET", "/series/lookup", params={"term": term})
        return [series_item(d) for d in data or []]

    async def list_series(self) -> list[MediaItem]:
        data = await self._json("GET", "/series")
        return [series_item(d) for d in data or []]

    async def _language_profile_id(self) -> int | None:
        """Sonarr v3 needs a languageProfileId; v4 removed the endpoint. Returns None on v4."""
        try:
            profiles = await self._json("GET", "/languageprofile")
        except ServiceUnavailable:
            return None
        if isinstance(profiles, list) and profiles and isinstance(profiles[0], dict) and "id" in profiles[0]:
            return int(profiles[0]["id"])
        return None

    async def add_series(self, tvdb_id: int, *, root_folder: str | None = None,
                         quality_profile_id: int | None = None, search: bool = True,
                         monitor: str = "all") -> MediaItem:
        results = await self._json("GET", "/series/lookup", params={"term": f"tvdb:{tvdb_id}"})
        found = next((r for r in results or [] if r.get("tvdbId") == tvdb_id), (results or [None])[0])
        if not found:
            raise NotFound(f"Sonarr found no show with TVDB id {tvdb_id}",
                           explanation="The TV database has no entry with that id.",
                           fix="Search for the show again and pick it from the results.")
        if int(found.get("id") or 0) > 0:
            return series_item(found)  # already in the library
        root, profile = await self._default_root_and_profile(root_folder, quality_profile_id)
        body: dict[str, Any] = {
            **found,
            "qualityProfileId": profile,
            "rootFolderPath": root,
            "monitored": True,
            "seasonFolder": True,
            "seriesType": found.get("seriesType") or "standard",
            "addOptions": {"monitor": monitor, "searchForMissingEpisodes": search,
                           "searchForCutoffUnmetEpisodes": False},
        }
        lang = await self._language_profile_id()
        if lang is not None:
            body["languageProfileId"] = lang
        resp = await self._api("POST", "/series", json=body)
        return series_item(parse_json(resp, self.display_name))

    async def delete_series(self, series_id: int, delete_files: bool = False) -> None:
        await self._api("DELETE", f"/series/{series_id}",
                        params={"deleteFiles": str(delete_files).lower(), "addImportExclusion": "false"})
