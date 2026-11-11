"""Newest phone/desktop app release on GitHub, so the Android app can show a small "Update" button."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from app.core.safe_http import SafeAsyncClient

log = logging.getLogger("unifierr.client_release")
RELEASES = "https://api.github.com/repos/simplyzubair/unifierr/releases?per_page=20"
DOWNLOAD_PREFIX = "https://github.com/simplyzubair/unifierr/releases/download/"
FRESH_SECONDS = 6 * 3600  # GitHub allows 60 anonymous calls an hour; a few a day is plenty
RETRY_SECONDS = 1800

_cache: tuple[float, dict[str, Any] | None] = (0.0, None)


def pick(releases: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Newest `client-vX.Y.Z` release that has an Android APK."""
    for rel in releases:
        match = re.fullmatch(r"client-v(\d+\.\d+\.\d+)", str(rel.get("tag_name", "")))
        if not match or rel.get("draft"):
            continue
        for asset in rel.get("assets") or []:
            url = str(asset.get("browser_download_url", ""))
            if url.endswith(".apk") and url.startswith(DOWNLOAD_PREFIX):
                return {"version": match.group(1), "android_url": url}
    return None


async def latest() -> dict[str, Any] | None:
    global _cache
    checked_at, value = _cache
    if time.monotonic() - checked_at < (FRESH_SECONDS if value else RETRY_SECONDS) and checked_at:
        return value
    try:
        async with SafeAsyncClient(timeout=15) as client:
            resp = await client.get(RELEASES, headers={"Accept": "application/vnd.github+json"})
            resp.raise_for_status()
            value = pick(resp.json())
    except (httpx.HTTPError, OSError, ValueError) as exc:  # offline or rate-limited: just no button, try again later
        log.info("Could not check for a new app version: %s", exc)
        value = None
    _cache = (time.monotonic(), value)
    return value
