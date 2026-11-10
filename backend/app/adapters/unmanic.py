"""Unmanic (GPL-3) adapter: the library optimiser that re-encodes finished downloads.

Unifierr uses it to turn every movie into HEVC (H.265): about half the size of H.264 at the same picture quality,
so it streams without buffering on slow connections. The resolution is never lowered and files that are already
HEVC are skipped. Unmanic has no API key; it is only reachable on the internal Docker network.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any, ClassVar

from app.adapters._arr_common import failed_status, parse_json
from app.adapters.base import BaseAdapter, HealthStatus, ServiceKind
from app.core.errors import ServiceUnavailable

PLUGIN = "video_transcoder"  # "Transcode Video Files", from Unmanic's official plugin repository
CHECK = "unifierr_verify"  # our own: skip already-efficient files, verify the copy before it replaces anything
CHECK_SOURCE = (Path(__file__).with_name("unmanic_verify_plugin.py")).read_text(encoding="utf-8")
# x265 "fast" keeps a 2-4 core NAS usable (about twice as fast as "medium", files ~5% bigger);
# CRF 23 is the encoder's own "visually close to the source" default.
TRANSCODE = {
    "mode": "standard", "video_codec": "hevc", "video_encoder": "libx265", "preset": "fast",
    "constant_quality_scale": "23", "target_resolution": "source", "keep_container": True,
    "force_transcode": False,
}


def check_plugin_files(jellyfin: tuple[str, str] | None) -> tuple[str, dict[str, str]]:
    """(version, zip contents). The version changes whenever the code or the Jellyfin details change,
    so Unifierr re-uploads exactly when needed."""
    config = json.dumps({"jellyfin_url": jellyfin[0], "jellyfin_api_key": jellyfin[1]} if jellyfin else {})
    version = "1.0.0-" + hashlib.sha256((CHECK_SOURCE + config).encode()).hexdigest()[:8]
    info = {
        "id": CHECK, "name": "Unifierr safety check", "author": "Unifierr", "version": version,
        "compatibility": [2], "platform": ["all"], "tags": "library file test,video",
        "description": "Skips files that are already efficient, and only lets a converted copy replace the "
                       "original when it plays, keeps the resolution, length, audio and subtitles, and is smaller.",
        "icon": "", "priorities": {"on_library_management_file_test": 0, "on_worker_process": 99},
    }
    return version, {"info.json": json.dumps(info, indent=1), "plugin.py": CHECK_SOURCE,
                     "unifierr.json": config, "requirements.txt": ""}


def zipped(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:  # Unmanic wants the files at the zip root
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


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

    async def ensure_converter(self, library_path: str, jellyfin: tuple[str, str] | None = None) -> None:
        """Idempotent: one library on `library_path` that watches for new files and converts with TRANSCODE,
        one worker (one movie at a time). `jellyfin` = (url, api key) lets the safety check wait until nobody is
        watching a movie before replacing it."""
        installed = {p.get("plugin_id"): p for p in
                     (await self._json("POST", "/plugins/installed", {"length": 100})).get("results", [])}
        if PLUGIN not in installed:
            await self._json("POST", "/plugins/repos/reload", {})
            await self._json("POST", "/plugins/install", {"plugin_id": PLUGIN})
        version, files = check_plugin_files(jellyfin)
        if installed.get(CHECK, {}).get("version") != version:
            resp = await self._request("POST", "/unmanic/api/v2/upload/plugin/file",
                                       files={"fileName": (f"{CHECK}.zip", zipped(files), "application/zip")})
            parse_json(resp, self.display_name)

        libraries = (await self._json("GET", "/settings/libraries"))["libraries"]
        library = next((lib for lib in libraries if lib.get("path") == library_path), None) or libraries[0]
        await self._json("POST", "/settings/library/write", {
            "library_config": {**library, "name": "Movies", "path": library_path,
                               "enable_scanner": True, "enable_inotify": True},
            "plugins": {"enabled_plugins": [{"library_id": library["id"], "plugin_id": p} for p in (CHECK, PLUGIN)]},
        })
        # Order matters. Deciding: the check speaks first (Unmanic takes the first yes/no answer). After encoding:
        # the check runs last, on the finished copy, before Unmanic is allowed to replace the original.
        for plugin_type, order in (("library_management.file_test", (CHECK, PLUGIN)),
                                   ("worker.process", (PLUGIN, CHECK))):
            current = await self._json("POST", "/plugins/flow", {"plugin_type": plugin_type,
                                                                  "library_id": library["id"]})
            by_id = {item["plugin_id"]: item for item in current.get("results", [])}  # save needs full records
            await self._json("POST", "/plugins/flow/save", {
                "plugin_type": plugin_type, "library_id": library["id"],
                "plugin_flow": [by_id[p] for p in order if p in by_id]})

        info = await self._json("POST", "/plugins/info", {"plugin_id": PLUGIN, "library_id": library["id"]})
        settings = [dict(s, value=TRANSCODE[s["key"]]) for s in info.get("settings", []) if s.get("key") in TRANSCODE]
        await self._json("POST", "/plugins/settings/update",
                         {"plugin_id": PLUGIN, "library_id": library["id"], "settings": settings})

        if not (await self._json("GET", "/settings/worker_groups"))["worker_groups"]:
            await self._json("POST", "/settings/worker_group/write", {
                "id": None, "name": "Unifierr", "number_of_workers": 1, "locked": False, "tags": [],
                "worker_event_schedules": []})
