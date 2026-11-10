"""Ask admins whether old, watched movies should be removed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import ServiceKind
from app.core.errors import UnifierrError
from app.services.common import adapter_for, get_services, get_setting, log_event, set_settings
from app.services.media import delete_library_item

REVIEW_DAYS = 90


async def due_movies(db: AsyncSession) -> list[dict[str, Any]]:
    radarrs = await get_services(db, ServiceKind.radarr, enabled_only=True)
    jellyfin = next(
        (service for service in await get_services(db, ServiceKind.jellyfin, enabled_only=True) if service.api_key_enc),
        None,
    )
    if not radarrs or jellyfin is None:
        return []

    now = datetime.now(UTC)
    snoozed = await get_setting(db, "cleanup_snoozed_until") or {}
    # shortcut: Plex watched state not supported yet
    async with adapter_for(db, ServiceKind.jellyfin, service_id=jellyfin.id) as jf:
        watched = await jf.played_movie_tmdb_ids()

    due: list[dict[str, Any]] = []
    async with adapter_for(db, ServiceKind.radarr) as arr:
        for movie in await arr.list_movies():
            if not movie.has_file or not movie.file_added_at or not movie.tmdb_id or not movie.external_id:
                continue
            if movie.tmdb_id not in watched:
                continue
            try:
                downloaded = datetime.fromisoformat(movie.file_added_at.replace("Z", "+00:00"))
                if downloaded.tzinfo is None:
                    downloaded = downloaded.replace(tzinfo=UTC)
                else:
                    downloaded = downloaded.astimezone(UTC)
                snooze_value = snoozed.get(str(movie.tmdb_id))
                snooze = datetime.fromisoformat(snooze_value.replace("Z", "+00:00")) if snooze_value else None
            except (TypeError, ValueError):
                continue
            if now < downloaded + timedelta(days=REVIEW_DAYS) or (snooze and now < snooze):
                continue
            due.append(
                {
                    "external_id": movie.external_id,
                    "tmdb_id": movie.tmdb_id,
                    "title": movie.title,
                    "year": movie.year,
                    "poster_url": movie.poster_url,
                    "downloaded_at": downloaded.isoformat(),
                    "days_since_download": (now - downloaded).days,
                }
            )
    return sorted(due, key=lambda item: item["downloaded_at"])


async def answer(db: AsyncSession, external_id: int, delete: bool, who: str) -> None:
    async with adapter_for(db, ServiceKind.radarr) as arr:
        movie = next((item for item in await arr.list_movies() if item.external_id == external_id), None)
    if movie is None or movie.tmdb_id is None:
        raise UnifierrError("Movie not found", status_code=404)

    snoozed = dict(await get_setting(db, "cleanup_snoozed_until") or {})
    if delete:
        await delete_library_item(db, "movie", external_id, delete_files=True)
        snoozed.pop(str(movie.tmdb_id), None)
        await set_settings(db, {"cleanup_snoozed_until": snoozed})
        await log_event(db, "cleanup", f"{who} deleted watched movie {movie.title} and its files.")
    else:
        snoozed[str(movie.tmdb_id)] = (datetime.now(UTC) + timedelta(days=REVIEW_DAYS)).isoformat()
        await set_settings(db, {"cleanup_snoozed_until": snoozed})
        await log_event(db, "cleanup", f"{who} kept watched movie {movie.title}; it will be reviewed again in 90 days.")
