"""Search again for wanted movies/episodes that have no file yet.

Radarr and Sonarr search once when something is requested; after that they only catch brand-new uploads (RSS).
If that first search found nothing usable (indexer down, release not out yet), the title waits forever.
"""
from __future__ import annotations

import asyncio
import logging

from app.adapters.base import ServiceKind
from app.core.db import sessionmaker
from app.core.errors import UnifierrError
from app.services.common import adapter_for

log = logging.getLogger("unifierr.retry_missing")
EVERY_SECONDS = 12 * 3600  # twice a day is gentle on indexers
COMMANDS = {ServiceKind.radarr: "MissingMoviesSearch", ServiceKind.sonarr: "MissingEpisodeSearch"}


async def search_missing_once() -> None:
    async with sessionmaker()() as db:
        for kind, command in COMMANDS.items():
            try:
                async with adapter_for(db, kind, required=False) as arr:
                    if arr:
                        await arr._json("POST", "/command", json={"name": command})
            except UnifierrError as exc:
                log.info("Could not ask %s to search for missing titles: %s", kind, exc)


async def retry_missing_loop() -> None:
    await asyncio.sleep(600)  # let everything start first
    while True:
        await search_missing_once()
        await asyncio.sleep(EVERY_SECONDS)
