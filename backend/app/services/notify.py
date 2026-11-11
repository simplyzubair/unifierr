"""Phone alert when a requested movie or show is ready to watch (via ntfy, https://ntfy.sh)."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.db import sessionmaker
from app.core.safe_http import SafeAsyncClient
from app.models import MediaRequest
from app.services.common import get_setting, set_settings
from app.services.request_progress import progress_for_requests

log = logging.getLogger("unifierr.notify")
CHECK_SECONDS = 300
RECENT_DAYS = 30  # only requests from the last month, so turning alerts on does not flood old ones


async def send(url: str, title: str, message: str) -> None:
    # SafeAsyncClient refuses private/metadata addresses, so an admin-typed URL cannot reach internal services.
    async with SafeAsyncClient(timeout=15) as client:
        resp = await client.post(url, content=message.encode(), headers={"Title": title, "Tags": "clapper"})
        resp.raise_for_status()


async def check_once() -> None:
    async with sessionmaker()() as db:
        url = await get_setting(db, "ntfy_url")
        if not url:
            return
        notified = set(await get_setting(db, "notified_requests") or [])
        since = datetime.now(UTC) - timedelta(days=RECENT_DAYS)
        rows = [r for r in (await db.execute(select(MediaRequest).where(MediaRequest.status == "approved"))).scalars()
                if r.id not in notified and (r.created_at.replace(tzinfo=UTC) if r.created_at.tzinfo is None
                                             else r.created_at) >= since]
        if not rows:
            return
        progress = await progress_for_requests(db, rows)
        for request in rows:
            if progress.get(request.id, ("",))[0] != "available":
                continue
            name = f"{request.title} ({request.year})" if request.year else request.title
            await send(url, "Ready to watch", f"{name} is in your library now. Enjoy!")
            notified.add(request.id)
            await set_settings(db, {"notified_requests": sorted(notified)})


async def notify_loop() -> None:
    await asyncio.sleep(90)
    while True:
        try:
            await check_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("Could not send ready-to-watch alerts", exc_info=True)
        await asyncio.sleep(CHECK_SECONDS)
