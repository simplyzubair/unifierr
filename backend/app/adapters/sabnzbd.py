"""SABnzbd adapter (API v4, mode=...&output=json, apikey auth).

Works with SABnzbd 3.x and 4.x, including the linuxserver container, whose web UI sits at "/"
and whose API key lives in sabnzbd.ini under [misc].
"""
from __future__ import annotations

import re
from typing import Any, ClassVar

from app.adapters._arr_common import failed_status, parse_json
from app.adapters.base import (
    BaseAdapter,
    Connection,
    HealthStatus,
    QueueItem,
    ServiceKind,
)
from app.core.errors import ServiceUnavailable

# SABnzbd slot status -> Unifierr state
STATE_MAP: dict[str, str] = {
    "Downloading": "downloading",
    "Grabbing": "checking",  # fetching the NZB itself
    "Queued": "queued",
    "Paused": "paused",
    "Failed": "error",
    "Completed": "completed",
    "Verifying": "checking", "Repairing": "checking", "Unpacking": "checking", "Extracting": "checking",
    "Fetching": "checking", "Propagating": "checking", "Moving": "checking",
    "Checking": "checking",
}
_STATUS_ERRORS = {
    "Failed": "SABnzbd could not download this item. Check its history inside SABnzbd for the reason.",
}

# "1.2 GB", "500 MB", "800 K", "123 B" (SABnzbd 4 uses binary units like "GiB" since 4.0)
_SIZE_RE = re.compile(r"^\s*([\d.,]+)\s*([KMGTPE]?(?:i?B)?)\s*$", re.IGNORECASE)
_UNITS = {"": 1, "B": 1, "K": 1024, "KB": 1024, "KIB": 1024, "M": 1024**2, "MB": 1024**2, "MIB": 1024**2,
          "G": 1024**3, "GB": 1024**3, "GIB": 1024**3, "T": 1024**4, "TB": 1024**4, "TIB": 1024**4,
          "P": 1024**5, "PB": 1024**5, "PIB": 1024**5, "E": 1024**6, "EB": 1024**6, "EIB": 1024**6}


def parse_size(value: str | None) -> int | None:
    """SABnzbd's human-readable size ('1.2 GB') -> bytes."""
    if not value:
        return None
    m = _SIZE_RE.match(str(value).strip())
    if not m:
        return None
    try:
        number = float(m.group(1).replace(",", "."))
        return int(number * _UNITS[m.group(2).upper()])
    except (ValueError, KeyError):
        return None


def parse_eta(value: str | None) -> int | None:
    """SABnzbd eta ('0:12:34' or '1.02:03:04') -> seconds. 'unknown' / missing -> None."""
    from app.adapters._arr_common import parse_timeleft

    if not value or str(value).strip().lower() == "unknown":
        return None
    return parse_timeleft(str(value))


class SabnzbdAdapter(BaseAdapter):
    kind: ClassVar[ServiceKind] = ServiceKind.sabnzbd
    display_name: ClassVar[str] = "SABnzbd"
    default_port: ClassVar[int] = 8080

    # ---- http ----
    async def _api(self, mode: str, **params: Any) -> Any:
        """Call SABnzbd's API and decode the JSON envelope, mapping errors to ServiceUnavailable."""
        params.setdefault("output", "json")
        params.setdefault("apikey", self.conn.api_key or "")
        resp = await self._request("GET", "/api", params={k: v for k, v in params.items() if v is not None})
        data = parse_json(resp, self.display_name)
        if not isinstance(data, dict):
            raise ServiceUnavailable(
                f"{self.display_name} sent an unexpected answer",
                explanation=f"{self.display_name} answered, but not with the data Unifierr expected.",
                fix=f"Update {self.display_name} to the latest version, then try again.",
            )
        if data.get("error"):
            raise ServiceUnavailable(
                f"{self.display_name} refused the request",
                explanation=str(data["error"])[:300] or None,
                fix="Check the API key in Settings → Apps → SABnzbd.",
            )
        if not bool(data.get("status", False)):
            raise ServiceUnavailable(f"{self.display_name} reported a problem with the request")
        return data

    async def _queue_raw(self, **extra: Any) -> dict[str, Any]:
        data = await self._api("queue", start="0", limit="200", **extra)
        queue = data.get("queue")
        return queue if isinstance(queue, dict) else {}

    # ---- BaseAdapter ----
    async def ping(self) -> HealthStatus:
        try:
            data = await self._api("version")
        except ServiceUnavailable as exc:
            return failed_status(exc, "sabnzbd")
        version = str(data.get("version") or "").lstrip("v") or None
        return HealthStatus(ok=True, version=version, message="Connected")

    # ---- queue ----
    async def queue(self) -> list[QueueItem]:
        raw = await self._queue_raw()
        return [self._item(s) for s in raw.get("slots") or [] if isinstance(s, dict)]

    @staticmethod
    def _item(s: dict[str, Any]) -> QueueItem:
        nzo_id = str(s.get("nzo_id") or "")
        raw_status = str(s.get("status") or "")
        state = STATE_MAP.get(raw_status, "unknown")
        size = parse_size(s.get("size"))
        sizeleft = parse_size(s.get("sizeleft"))
        percent = s.get("percentage")
        try:
            progress = float(str(percent).rstrip("%")) if percent not in (None, "") else 0.0
        except ValueError:
            progress = 0.0
        return QueueItem(
            id=f"sabnzbd:{nzo_id}",
            name=str(s.get("filename") or nzo_id or "Unknown"),
            source="sabnzbd",
            state=state,  # type: ignore[arg-type]
            progress=round(max(0.0, min(100.0, progress)), 1),
            size=size,
            downloaded=max(size - sizeleft, 0) if size and sizeleft is not None else None,
            eta_seconds=parse_eta(s.get("eta")),
            category=str(s.get("cat") or "") or None,
            error=s.get("fail_message") or _STATUS_ERRORS.get(raw_status),
        )

    # ---- actions ----
    async def _queue_action(self, name: str, nzo_ids: list[str], **extra: Any) -> None:
        for nzo_id in nzo_ids:
            await self._api("queue", name=name, value=nzo_id, **extra)

    async def pause(self, ids: list[str]) -> None:
        await self._queue_action("pause", ids)

    async def resume(self, ids: list[str]) -> None:
        await self._queue_action("resume", ids)

    async def retry(self, ids: list[str]) -> None:
        # SABnzbd >= 3.4 accepts a per-item nzo_id with mode=retry; older versions retry everything.
        for nzo_id in ids:
            await self._api("retry", value=nzo_id)

    async def delete(self, ids: list[str], delete_files: bool = False) -> None:
        await self._queue_action("delete", ids, del_files=1 if delete_files else 0)

    async def transfer_info(self) -> dict[str, Any]:
        """Download speed and pause state. Usenet does not upload, so up_speed is always 0."""
        raw = await self._queue_raw()
        kbpersec = raw.get("kbpersec")
        try:
            dl_speed = int(float(kbpersec) * 1024)
        except (TypeError, ValueError):
            dl_speed = 0
        return {"dl_speed": dl_speed, "up_speed": 0, "paused": bool(raw.get("paused", False))}

    # ---- categories ----
    async def categories(self) -> list[dict[str, Any]]:
        """All categories with their name and folder (None when the folder is the default)."""
        data = await self._api("get_cats")
        out: list[dict[str, Any]] = []
        for cat in data.get("categories") or []:
            if isinstance(cat, dict):
                out.append({"name": cat.get("name"), "folder": cat.get("dir") or None})
        return out

    async def ensure_category(self, name: str, folder: str) -> None:
        """Create or update a category so downloads for `name` land in `folder`. Idempotent."""
        for cat in await self.categories():
            if str(cat.get("name") or "").lower() == name.lower():
                if cat.get("folder") == folder:
                    return
                await self._api("change_cat", name=name, dir=folder)
                return
        await self._api("add_cat", name=name, dir=folder)

    # ---- pause / resume the whole client (used by the wiring to keep things untouched) ----
    async def server_paused(self) -> bool:
        raw = await self._queue_raw()
        return bool(raw.get("paused", False))
