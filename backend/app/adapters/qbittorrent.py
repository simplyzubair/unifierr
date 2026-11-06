"""qBittorrent adapter (WebUI API v2, cookie login). Works with 4.6 and 5.x."""
from __future__ import annotations

import json
from typing import Any, ClassVar

import httpx

from app.adapters._arr_common import failed_status, parse_json, raw_request
from app.adapters.base import (
    BaseAdapter,
    Connection,
    HealthStatus,
    QueueItem,
    ServiceKind,
)
from app.core.errors import ServiceUnavailable

# qBittorrent torrent state -> Unifierr state
STATE_MAP: dict[str, str] = {
    "downloading": "downloading", "forcedDL": "downloading", "metaDL": "downloading", "forcedMetaDL": "downloading",
    "stalledDL": "stalled",
    "pausedDL": "paused", "stoppedDL": "paused",
    "uploading": "seeding", "forcedUP": "seeding", "stalledUP": "seeding",
    "pausedUP": "completed", "stoppedUP": "completed",
    "queuedDL": "queued", "queuedUP": "queued",
    "checkingDL": "checking", "checkingUP": "checking", "checkingResumeData": "checking",
    "allocating": "checking", "moving": "checking",
    "error": "error", "missingFiles": "error",
}
_STATE_ERRORS = {
    "error": "qBittorrent reports an error with this download. Check its log inside qBittorrent.",
    "missingFiles": "The downloaded files are missing from disk. They may have been moved or deleted.",
}
_ETA_NEVER = 8640000  # qBittorrent's "infinity"


class QbittorrentAdapter(BaseAdapter):
    kind: ClassVar[ServiceKind] = ServiceKind.qbittorrent
    display_name: ClassVar[str] = "qBittorrent"
    default_port: ClassVar[int] = 8080

    def __init__(self, conn: Connection, client: httpx.AsyncClient | None = None):
        super().__init__(conn, client)
        self._sid: str | None = None
        self._new_api: bool | None = None  # v5 renamed pause/resume to stop/start

    # ---- auth ----
    def _csrf_headers(self) -> dict[str, str]:
        base = self.conn.base_url.rstrip("/")
        return {"Referer": base, "Origin": base}

    async def login(self) -> None:
        resp = await raw_request(
            self, "POST", "/api/v2/auth/login", headers=self._csrf_headers(),
            data={"username": self.conn.username or "", "password": self.conn.password or ""},
        )
        if resp.status_code == 403:
            raise ServiceUnavailable(
                "qBittorrent has temporarily blocked Unifierr",
                explanation="qBittorrent bans an address for a while after too many wrong login attempts "
                            "(the username or password was probably wrong several times).",
                fix="Wait about an hour or restart qBittorrent, then fix the username and password in "
                    "Settings → Apps → qBittorrent.",
            )
        if resp.status_code >= 400:
            raise ServiceUnavailable(f"qBittorrent returned an error ({resp.status_code})")
        if resp.text.strip().lower().startswith("fails"):
            raise ServiceUnavailable(
                "qBittorrent rejected the username or password",
                explanation="qBittorrent answered, but the login was refused.",
                fix="Enter the right qBittorrent username and password in Settings → Apps → qBittorrent.",
            )
        sid = resp.cookies.get("SID")
        if sid:
            self._sid = sid
        elif self._sid is None:
            # No cookie: qBittorrent may have authentication bypass on for our address. Carry on without one.
            self._sid = ""

    async def _call(self, method: str, path: str, **kw: Any) -> httpx.Response:
        """Authenticated request; logs in on first use and re-logs in once when the session expired (403)."""
        if self._sid is None:
            await self.login()
        extra = kw.pop("headers", {})
        for attempt in (1, 2):
            headers = {**self._csrf_headers(), **extra}
            if self._sid:
                headers["Cookie"] = f"SID={self._sid}"
            resp = await raw_request(self, method, path, headers=headers, **kw)
            if resp.status_code == 403 and attempt == 1:
                self._sid = None
                await self.login()
                continue
            return resp
        raise AssertionError("unreachable")  # pragma: no cover

    async def _ok(self, method: str, path: str, **kw: Any) -> httpx.Response:
        resp = await self._call(method, path, **kw)
        if resp.status_code in (401, 403):
            raise ServiceUnavailable(
                "qBittorrent rejected the credentials",
                explanation="qBittorrent answered, but the username or password is wrong.",
                fix="Enter the right qBittorrent username and password in Settings → Apps → qBittorrent.",
            )
        if resp.status_code >= 400:
            raise ServiceUnavailable(f"qBittorrent returned an error ({resp.status_code})",
                                     explanation=resp.text[:300] or None)
        return resp

    # ---- BaseAdapter ----
    async def ping(self) -> HealthStatus:
        try:
            await self.login()
            resp = await self._ok("GET", "/api/v2/app/version")
        except ServiceUnavailable as exc:
            return failed_status(exc, "qbittorrent")
        return HealthStatus(ok=True, version=resp.text.strip().lstrip("v") or None, message="Connected")

    # ---- torrents ----
    async def torrents(self) -> list[QueueItem]:
        resp = await self._ok("GET", "/api/v2/torrents/info")
        return [self._item(t) for t in parse_json(resp, self.display_name) or []]

    @staticmethod
    def _item(t: dict[str, Any]) -> QueueItem:
        raw_state = str(t.get("state") or "")
        state = STATE_MAP.get(raw_state, "unknown")
        eta = t.get("eta")
        return QueueItem(
            id=str(t.get("hash", "")).lower(),
            name=str(t.get("name") or ""),
            source="qbittorrent",
            state=state,  # type: ignore[arg-type]
            progress=round(max(0.0, min(1.0, float(t.get("progress") or 0))) * 100, 1),
            size=t.get("size") if t.get("size") is not None else t.get("total_size"),
            downloaded=t.get("downloaded"),
            download_speed=t.get("dlspeed"),
            upload_speed=t.get("upspeed"),
            eta_seconds=int(eta) if isinstance(eta, int) and 0 <= eta < _ETA_NEVER else None,
            category=t.get("category") or None,
            save_path=t.get("save_path") or None,
            error=_STATE_ERRORS.get(raw_state),
        )

    @staticmethod
    def _hashes(hashes: list[str]) -> str:
        return "|".join(h.lower() for h in hashes)

    async def _pause_resume(self, new: str, old: str, hashes: list[str]) -> None:
        if not hashes:
            return
        data = {"hashes": self._hashes(hashes)}
        if self._new_api is not False:
            resp = await self._call("POST", f"/api/v2/torrents/{new}", data=data)
            if resp.status_code != 404:
                if resp.status_code >= 400:
                    raise ServiceUnavailable(f"qBittorrent returned an error ({resp.status_code})")
                self._new_api = True
                return
            self._new_api = False  # qBittorrent 4.x has no stop/start
        await self._ok("POST", f"/api/v2/torrents/{old}", data=data)

    async def pause(self, hashes: list[str]) -> None:
        await self._pause_resume("stop", "pause", hashes)

    async def resume(self, hashes: list[str]) -> None:
        await self._pause_resume("start", "resume", hashes)

    async def delete(self, hashes: list[str], delete_files: bool = False) -> None:
        if not hashes:
            return
        await self._ok("POST", "/api/v2/torrents/delete",
                       data={"hashes": self._hashes(hashes), "deleteFiles": str(delete_files).lower()})

    async def ensure_category(self, name: str, save_path: str) -> None:
        data = {"category": name, "savePath": save_path}
        resp = await self._call("POST", "/api/v2/torrents/createCategory", data=data)
        if resp.status_code == 409:  # already exists: make sure the save path is right
            await self._ok("POST", "/api/v2/torrents/editCategory", data=data)
        elif resp.status_code >= 400:
            raise ServiceUnavailable(f"qBittorrent returned an error ({resp.status_code})",
                                     explanation=resp.text[:300] or None)

    async def set_preferences(self, prefs: dict[str, Any]) -> None:
        await self._ok("POST", "/api/v2/app/setPreferences", data={"json": json.dumps(prefs)})

    async def transfer_info(self) -> dict[str, Any]:
        info = parse_json(await self._ok("GET", "/api/v2/transfer/info"), self.display_name) or {}
        return {"dl_speed": int(info.get("dl_info_speed") or 0), "up_speed": int(info.get("up_info_speed") or 0),
                "connection_status": info.get("connection_status")}
