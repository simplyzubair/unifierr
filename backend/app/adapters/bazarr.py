"""Bazarr 1.4+ adapter (subtitles). Header auth: X-API-KEY."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, ClassVar

import httpx

from app.adapters._arr_common import failed_status, parse_json
from app.adapters.base import (
    BaseAdapter,
    Connection,
    HealthIssue,
    HealthStatus,
    ServiceKind,
    SubtitleWanted,
)
from app.core.errors import ServiceUnavailable

log = logging.getLogger(__name__)

_EPISODE = re.compile(r"^(\d+)x(\d+)$")


def _rows(payload: Any) -> list[dict[str, Any]]:
    """Bazarr wraps lists in {"data": [...]}; older builds return the bare list."""
    if isinstance(payload, dict):
        payload = payload.get("data", [])
    return [r for r in payload if isinstance(r, dict)] if isinstance(payload, list) else []


def _lang_names(missing: Any) -> list[str]:
    out: list[str] = []
    for m in missing or []:
        if isinstance(m, dict):
            out.append(str(m.get("name") or m.get("code2") or m.get("code3") or ""))
        else:
            out.append(str(m))
    return [x for x in out if x]


def _episode_label(row: dict[str, Any]) -> str | None:
    num = str(row.get("episode_number") or "")
    m = _EPISODE.match(num)
    label = f"S{int(m.group(1)):02d}E{int(m.group(2)):02d}" if m else (num or None)
    title = row.get("episodeTitle")
    if label and title:
        return f"{label} - {title}"
    return label or (str(title) if title else None)


class BazarrAdapter(BaseAdapter):
    kind: ClassVar[ServiceKind] = ServiceKind.bazarr
    display_name: ClassVar[str] = "Bazarr"
    default_port: ClassVar[int] = 6767

    def __init__(self, conn: Connection, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(conn, client)
        self._headers = {"X-API-KEY": conn.api_key or "", "Accept": "application/json"}

    async def _api(self, method: str, path: str, **kw: Any) -> httpx.Response:
        headers = {**self._headers, **kw.pop("headers", {})}
        return await self._request(method, path, headers=headers, **kw)

    async def ping(self) -> HealthStatus:
        try:
            data = parse_json(await self._api("GET", "/api/system/status"), self.display_name)
        except ServiceUnavailable as exc:
            return failed_status(exc, "bazarr")
        info = data.get("data", data) if isinstance(data, dict) else {}
        return HealthStatus(ok=True, version=info.get("bazarr_version"), message="Connected")

    async def health_issues(self) -> list[HealthIssue]:
        rows = _rows(parse_json(await self._api("GET", "/api/system/health"), self.display_name))
        issues: list[HealthIssue] = []
        for r in rows:
            obj = str(r.get("object") or "")
            text = str(r.get("issue") or r.get("message") or "Unknown problem")
            issues.append(HealthIssue(
                severity="warning",
                message=f"{obj}: {text}" if obj else text,
                explanation="Bazarr reported this problem. Subtitles may not work until it is fixed.",
                fix="Open Bazarr → System → Status for details, or run 'Connect everything' in Unifierr again.",
                source="bazarr",
            ))
        return issues

    # ---- subtitles ----
    async def wanted(self) -> list[SubtitleWanted]:
        out: list[SubtitleWanted] = []
        params = {"start": "0", "length": "100"}
        movies = _rows(parse_json(await self._api("GET", "/api/movies/wanted", params=params), self.display_name))
        for r in movies:
            if r.get("radarrId") is None:
                continue
            out.append(SubtitleWanted(media_type="movie", title=str(r.get("title") or "Unknown"),
                                      missing_languages=_lang_names(r.get("missing_subtitles")),
                                      external_id=int(r["radarrId"])))
        episodes = _rows(parse_json(await self._api("GET", "/api/episodes/wanted", params=params), self.display_name))
        for r in episodes:
            if r.get("sonarrEpisodeId") is None:
                continue
            out.append(SubtitleWanted(media_type="series", title=str(r.get("seriesTitle") or "Unknown"),
                                      episode=_episode_label(r),
                                      missing_languages=_lang_names(r.get("missing_subtitles")),
                                      external_id=int(r["sonarrEpisodeId"])))
        return out

    async def search_all_missing(self) -> None:
        for task in ("wanted_search_missing_subtitles_movies", "wanted_search_missing_subtitles_series"):
            await self._api("POST", "/api/system/tasks", params={"taskid": task})

    # ---- configuration ----
    async def set_ui_login(self, username: str, password: str) -> None:
        """Require a login for Bazarr's web page. Bazarr stores the password hashed itself;
        the API key keeps working for Unifierr."""
        form = {
            "settings-auth-type": "form",
            "settings-auth-username": username,
            "settings-auth-password": password,
        }
        await self._api("POST", "/api/system/settings", data=form)

    async def ensure_arr_connection(self, *, kind: str, host: str, port: int, api_key: str,
                                    base_url: str = "/", ssl: bool = False) -> None:
        kind = str(kind).lower()
        if kind not in ("radarr", "sonarr"):
            raise ServiceUnavailable(f"Unsupported app for Bazarr: {kind}")
        if await self._arr_already_configured(kind, host, port, base_url, ssl, api_key):
            return
        form = {
            f"settings-general-use_{kind}": "true",
            f"settings-{kind}-ip": host,
            f"settings-{kind}-port": str(port),
            f"settings-{kind}-apikey": api_key,
            f"settings-{kind}-base_url": base_url,
            f"settings-{kind}-ssl": "true" if ssl else "false",
        }
        await self._api("POST", "/api/system/settings", data=form)

    async def _arr_already_configured(self, kind: str, host: str, port: int, base_url: str, ssl: bool,
                                      api_key: str) -> bool:
        """Best effort: skip the write when Bazarr already has exactly these values."""
        try:
            cur = parse_json(await self._api("GET", "/api/system/settings"), self.display_name)
            sect = cur.get(kind, {})
            return bool(
                cur.get("general", {}).get(f"use_{kind}") is True
                and sect.get("ip") == host and int(sect.get("port") or 0) == int(port)
                and sect.get("apikey") == api_key and bool(sect.get("ssl")) == ssl
                and (sect.get("base_url") or "/") == (base_url or "/")
            )
        except (ServiceUnavailable, AttributeError, ValueError, TypeError):
            return False

    async def ensure_default_language_profile(self, languages: list[str] | None = None) -> None:
        """Best effort: make a 'Unifierr' language profile and use it as the default for movies and series.

        Never raises: Bazarr's settings API differs between versions, so any surprise is logged and ignored.
        """
        langs = [str(x).lower() for x in (languages or ["en"])]
        try:
            profiles = parse_json(await self._api("GET", "/api/system/languages/profiles"), self.display_name)
            profiles = profiles if isinstance(profiles, list) else _rows(profiles)
            match = next((p for p in profiles
                          if {str(i.get("language")).lower() for i in p.get("items", [])} == set(langs)), None)
            if match is not None:
                profile_id = match["profileId"]
                new_profiles = None
            else:
                profile_id = max([int(p.get("profileId", 0)) for p in profiles] + [0]) + 1
                new_profiles = [*profiles, {
                    "profileId": profile_id, "name": "Unifierr", "cutoff": None, "mustContain": [],
                    "mustNotContain": [], "originalFormat": False,
                    "items": [{"id": n + 1, "language": code, "audio_exclude": "False", "hi": "False",
                               "forced": "False"} for n, code in enumerate(langs)],
                }]
            form: dict[str, Any] = {
                "languages-enabled": langs,  # sent as a repeated form key
                "settings-general-serie_default_enabled": "true",
                "settings-general-serie_default_profile": str(profile_id),
                "settings-general-movie_default_enabled": "true",
                "settings-general-movie_default_profile": str(profile_id),
            }
            if new_profiles is not None:
                form["languages-profiles"] = json.dumps(new_profiles)
            await self._api("POST", "/api/system/settings", data=form)
        except Exception as exc:  # noqa: BLE001 - best effort by contract
            log.warning("Could not set the default Bazarr language profile: %s", exc.__class__.__name__)
