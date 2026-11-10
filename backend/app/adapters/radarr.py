"""Radarr v5 adapter (API v3)."""
from __future__ import annotations

from typing import Any, ClassVar

from app.adapters._arr_common import ArrAdapter, parse_json, poster_from_images
from app.adapters.base import MediaItem, ServiceKind
from app.core.errors import NotFound


def movie_item(d: dict[str, Any]) -> MediaItem:
    """Map a Radarr movie / lookup resource to the normalized model."""
    mid = int(d.get("id") or 0)
    return MediaItem(
        media_type="movie",
        title=str(d.get("title") or "Unknown"),
        year=d.get("year") or None,
        overview=d.get("overview") or None,
        poster_url=poster_from_images(d.get("images")),
        tmdb_id=d.get("tmdbId") or None,
        imdb_id=d.get("imdbId") or None,
        external_id=mid or None,
        in_library=mid > 0,
        monitored=bool(d.get("monitored", False)),
        has_file=bool(d.get("hasFile", False)),
        file_added_at=(d.get("movieFile") or {}).get("dateAdded"),
        size_on_disk=d.get("sizeOnDisk") or None,
        status=d.get("status") or None,
    )


class RadarrAdapter(ArrAdapter):
    kind: ClassVar[ServiceKind] = ServiceKind.radarr
    display_name: ClassVar[str] = "Radarr"
    default_port: ClassVar[int] = 7878
    app_label: ClassVar[str] = "radarr"
    qbit_category_field: ClassVar[str] = "movieCategory"
    queue_params: ClassVar[dict[str, str]] = {"includeMovie": "true"}
    queue_media_type: ClassVar[str] = "movie"
    queue_source: ClassVar[str] = "radarr"
    queue_media_key: ClassVar[str] = "movie"

    async def lookup(self, term: str) -> list[MediaItem]:
        data = await self._json("GET", "/movie/lookup", params={"term": term})
        return [movie_item(d) for d in data or []]

    async def list_movies(self) -> list[MediaItem]:
        data = await self._json("GET", "/movie")
        return [movie_item(d) for d in data or []]

    async def add_movie(self, tmdb_id: int, *, root_folder: str | None = None,
                        quality_profile_id: int | None = None, search: bool = True) -> MediaItem:
        found = await self._json("GET", "/movie/lookup/tmdb", params={"tmdbId": tmdb_id})
        if isinstance(found, list):
            found = found[0] if found else None
        if not found:
            raise NotFound(f"Radarr found no movie with TMDB id {tmdb_id}",
                           explanation="The movie database has no entry with that id.",
                           fix="Search for the movie again and pick it from the results.")
        if int(found.get("id") or 0) > 0:
            return movie_item(found)  # already in the library: nothing to add
        root, profile = await self._default_root_and_profile(root_folder, quality_profile_id)
        body = {
            **found,
            "qualityProfileId": profile,
            "rootFolderPath": root,
            "monitored": True,
            "minimumAvailability": found.get("minimumAvailability") or "released",
            "addOptions": {"searchForMovie": search, "monitor": "movieOnly"},
        }
        resp = await self._api("POST", "/movie", json=body)
        return movie_item(parse_json(resp, self.display_name))

    async def delete_movie(self, movie_id: int, delete_files: bool = False) -> None:
        await self._api("DELETE", f"/movie/{movie_id}",
                        params={"deleteFiles": str(delete_files).lower(), "addImportExclusion": "false"})
