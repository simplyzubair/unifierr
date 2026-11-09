"""Unmanic (GPL-3) adapter: the library optimiser that re-encodes finished downloads.

Unifierr uses it to turn every movie into HEVC (H.265): about half the size of H.264 at the same picture quality,
so it streams without buffering on slow connections. The resolution is never lowered and files that are already
HEVC are skipped. Unmanic has no API key; it is only reachable on the internal Docker network.
"""
from __future__ import annotations

from typing import Any, ClassVar

from app.adapters._arr_common import failed_status, parse_json
from app.adapters.base import BaseAdapter, HealthStatus, ServiceKind
from app.core.errors import ServiceUnavailable

PLUGIN = "video_transcoder"  # "Transcode Video Files", from Unmanic's official plugin repository
# x265 "fast" keeps a 2-4 core NAS usable (about twice as fast as "medium", files ~5% bigger);
# CRF 23 is the encoder's own "visually close to the source" default.
TRANSCODE = {
    "mode": "standard", "video_codec": "hevc", "video_encoder": "libx265", "preset": "fast",
    "constant_quality_scale": "23", "target_resolution": "source", "keep_container": True,
    "force_transcode": False,
}


class UnmanicAdapter(BaseAdapter):
    kind: ClassVar[ServiceKind] = ServiceKind.unmanic
    display_name: ClassVar[str] = "Unmanic"
    default_port: ClassVar[int] = 8888

    async def _json(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        resp = await self._request(method, f"/unmanic/api/v2{path}", json=body)
        data = parse_json(resp, self.display_name)
        if isinstance(data, dict) and data.get("error"):
            raise ServiceUnavailable(f"Unmanic refused a setting: {data['error']}", explanation=str(data)[:300])
        return data

    async def ping(self) -> HealthStatus:
        try:
            data = await self._json("GET", "/version/read")
        except ServiceUnavailable as exc:
            return failed_status(exc, "unmanic")
        return HealthStatus(ok=True, version=data.get("version"), message="Connected")

    async def ensure_converter(self, library_path: str) -> None:
        """Idempotent: one library on `library_path` that watches for new files and converts with TRANSCODE,
        one worker (one movie at a time)."""
        installed = await self._json("POST", "/plugins/installed", {"length": 100})
        if PLUGIN not in {p.get("plugin_id") for p in installed.get("results", [])}:
            await self._json("POST", "/plugins/repos/reload", {})
            await self._json("POST", "/plugins/install", {"plugin_id": PLUGIN})

        libraries = (await self._json("GET", "/settings/libraries"))["libraries"]
        library = next((lib for lib in libraries if lib.get("path") == library_path), None) or libraries[0]
        await self._json("POST", "/settings/library/write", {
            "library_config": {**library, "name": "Movies", "path": library_path,
                               "enable_scanner": True, "enable_inotify": True},
            "plugins": {"enabled_plugins": [{"library_id": library["id"], "plugin_id": PLUGIN}]},
        })

        info = await self._json("POST", "/plugins/info", {"plugin_id": PLUGIN, "library_id": library["id"]})
        settings = [dict(s, value=TRANSCODE[s["key"]]) for s in info.get("settings", []) if s.get("key") in TRANSCODE]
        await self._json("POST", "/plugins/settings/update",
                         {"plugin_id": PLUGIN, "library_id": library["id"], "settings": settings})

        if not (await self._json("GET", "/settings/worker_groups"))["worker_groups"]:
            await self._json("POST", "/settings/worker_group/write", {
                "id": None, "name": "Unifierr", "number_of_workers": 1, "locked": False, "tags": [],
                "worker_event_schedules": []})
