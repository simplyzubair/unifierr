"""NZBGet adapter (JSON-RPC, /jsonrpc).

NZBGet 21+ answers JSON-RPC at /jsonrpc. Every method takes username/password as the first two
params (required when a restricted user is configured, which is the linuxserver default).
Group actions go through editqueue with EditCommand = GroupPause/GroupResume/GroupDelete/
GroupReturnToQueue and EditText = the NZBID.
"""
from __future__ import annotations

import re
from typing import Any, ClassVar

import httpx

from app.adapters._arr_common import failed_status, parse_json
from app.adapters.base import (
    BaseAdapter,
    Connection,
    HealthStatus,
    QueueItem,
    ServiceKind,
)
from app.core.errors import ServiceUnavailable

# NZBGet group status -> Unifierr state
STATE_MAP: dict[str, str] = {
    "DOWNLOADING": "downloading",
    "FETCHING": "checking",  # fetching the NZB itself
    "QUEUED": "queued",
    "PAUSED": "paused",
    "FAILURE": "error", "WARNING": "error",
    "COMPLETED": "completed",
    "COMPLETING": "checking", "VERIFYING": "checking", "REPAIRING": "checking",
    "UNPACKING": "checking", "MOVING": "checking", "FINALIZING": "checking", "CHECKING": "checking",
    "DELETING": "checking", "QUARANTINED": "error",
}


class NzbgetAdapter(BaseAdapter):
    kind: ClassVar[ServiceKind] = ServiceKind.nzbget
    display_name: ClassVar[str] = "NZBGet"
    default_port: ClassVar[int] = 6789

    # ---- http ----
    async def _rpc(self, method: str, *params: Any) -> Any:
        """Call the JSON-RPC endpoint, mapping errors to ServiceUnavailable."""
        payload = {"version": "1.1", "method": method, "params": list(params)}
        try:
            resp = await self.client.request(
                "POST", self._url("/jsonrpc"), json=payload, timeout=self.conn.timeout
            )
        except httpx.ConnectError as exc:
            raise ServiceUnavailable(
                f"Cannot reach {self.display_name}",
                explanation=f"Unifierr could not open a connection to {self.display_name} at {self.conn.base_url}.",
                fix=f"Make sure {self.display_name} is running and that the address is correct.",
            ) from exc
        except httpx.TimeoutException as exc:
            raise ServiceUnavailable(
                f"{self.display_name} did not answer in time",
                explanation=f"{self.display_name} is reachable but too slow or stuck.",
                fix=f"Restart {self.display_name}. If it keeps happening, check its logs.",
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailable(f"Error talking to {self.display_name}: {exc.__class__.__name__}") from exc
        if resp.status_code in (401, 403):
            raise ServiceUnavailable(
                f"{self.display_name} rejected the credentials",
                explanation=f"{self.display_name} answered, but the control username or password is wrong.",
                fix="Enter the right control username and password in Settings → Apps → NZBGet.",
            )
        if resp.status_code >= 400:
            raise ServiceUnavailable(f"{self.display_name} returned an error ({resp.status_code})",
                                     explanation=resp.text[:300] or None)
        data = parse_json(resp, self.display_name)
        if isinstance(data, dict) and data.get("error") is not None:
            raise ServiceUnavailable(
                f"{self.display_name} refused the request",
                explanation=str(data.get("error") or {}).get("message") if isinstance(data.get("error"), dict)
                else str(data.get("error"))[:300] or None,
            )
        if isinstance(data, dict):
            return data.get("result")
        return data

    def _auth(self) -> list[str | None]:
        return [self.conn.username or None, self.conn.password or None]

    # ---- BaseAdapter ----
    async def ping(self) -> HealthStatus:
        try:
            version = await self._rpc("version", *self._auth())
        except ServiceUnavailable as exc:
            return failed_status(exc, "nzbget")
        return HealthStatus(ok=True, version=str(version or "").lstrip("v") or None, message="Connected")

    # ---- queue ----
    async def queue(self) -> list[QueueItem]:
        groups = await self._rpc("listgroups", *self._auth(), 0)
        return [self._item(g) for g in groups or [] if isinstance(g, dict)]

    @staticmethod
    def _file_bytes(group: dict[str, Any], field: str) -> int | None:
        lo = group.get(f"{field}Lo")
        hi = group.get(f"{field}Hi")
        if isinstance(lo, int) and isinstance(hi, int):
            return (hi << 30) + lo
        mb = group.get(f"{field}MB")
        return int(mb * 1024 * 1024) if isinstance(mb, (int, float)) else None

    def _item(self, g: dict[str, Any]) -> QueueItem:
        nzb_id = str(g.get("NZBID") or "")
        raw_status = str(g.get("Status") or "").upper()
        state = STATE_MAP.get(raw_status, "unknown")
        size = self._file_bytes(g, "FileSize")
        remaining = self._file_bytes(g, "RemainingSize")
        downloaded = max(size - remaining, 0) if size and remaining is not None else None
        progress = round(downloaded / size * 100, 1) if size and downloaded is not None else 0.0
        error: str | None = None
        if state == "error" or raw_status in ("FAILURE", "QUARANTINED", "WARNING"):
            messages = g.get("Messages") or []
            error = "; ".join(str(m.get("Text") or m) for m in messages if isinstance(m, dict)) or (
                "This download failed. Check its history inside NZBGet for the reason."
            )
        return QueueItem(
            id=f"nzbget:{nzb_id}",
            name=str(g.get("NZBName") or g.get("Name") or nzb_id or "Unknown"),
            source="nzbget",
            state=state,  # type: ignore[arg-type]
            progress=max(0.0, min(100.0, progress)),
            size=size,
            downloaded=downloaded,
            eta_seconds=None,  # NZBGet does not expose a per-item ETA
            category=str(g.get("Category") or "") or None,
            save_path=str(g.get("DestDir") or "") or None,
            error=error,
        )

    # ---- actions ----
    async def _edit(self, command: str, nzb_ids: list[str], offset: int = 0, text: str = "") -> None:
        for nzb_id in nzb_ids:
            await self._rpc("editqueue", *self._auth(), command, offset, nzb_id or text)

    async def pause(self, ids: list[str]) -> None:
        await self._edit("GroupPause", ids)

    async def resume(self, ids: list[str]) -> None:
        await self._edit("GroupResume", ids)

    async def retry(self, ids: list[str]) -> None:
        # Return failed groups to the queue so they download again.
        await self._edit("GroupReturnToQueue", ids)

    async def delete(self, ids: list[str], delete_files: bool = False) -> None:
        # GroupFinalDelete also removes already-downloaded files; GroupDelete just removes the queue entry.
        await self._edit("GroupFinalDelete" if delete_files else "GroupDelete", ids)

    async def transfer_info(self) -> dict[str, Any]:
        status = await self._rpc("status", *self._auth()) or {}
        paused = bool(status.get("ServerPaused") and status.get("PostPaused"))
        return {
            "dl_speed": int(status.get("DownloadRate") or 0),
            "up_speed": 0,  # Usenet does not upload.
            "paused": paused,
        }

    # ---- categories ----
    async def config_entries(self) -> list[dict[str, Any]]:
        entries = await self._rpc("config", *self._auth()) or []
        return [e for e in entries if isinstance(e, dict)]

    async def categories(self) -> list[dict[str, Any]]:
        """The configured categories (name + destination folder). NZBGet creates categories on the
        fly when a download arrives with an unknown category, so this list may be incomplete."""
        entries = await self.config_entries()
        out: list[dict[str, Any]] = []
        for e in entries:
            m = re.fullmatch(r"Category(\d+)\.Name", str(e.get("Name") or ""))
            if m:
                dest_name = f"Category{m.group(1)}.DestDir"
                dest = next((x.get("Value") for x in entries if x.get("Name") == dest_name), None)
                out.append({"name": e.get("Value"), "folder": dest or None})
        return out

    async def ensure_category(self, name: str, folder: str) -> None:
        """Make sure the category exists with the right destination folder.

        A missing category is left alone (NZBGet auto-creates it when the first download arrives);
        an existing one with the wrong destination folder is corrected.
        """
        entries = await self.config_entries()
        for e in entries:
            m = re.fullmatch(r"Category(\d+)\.Name", str(e.get("Name") or ""))
            if m and str(e.get("Value") or "").lower() == name.lower():
                dest_name = f"Category{m.group(1)}.DestDir"
                dest = next((x.get("Value") for x in entries if x.get("Name") == dest_name), None)
                if dest is not None and str(dest or "") != folder:
                    await self._rpc("setconfig", *self._auth(), dest_name, folder)
                return
