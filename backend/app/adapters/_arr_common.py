"""Shared logic for the *arr family (Radarr, Sonarr, Prowlarr) plus small helpers every adapter uses.

Nothing here talks to a specific app's media model; Radarr/Sonarr/Prowlarr subclasses add that.
Secrets (API keys, passwords) are never written into exception messages or logs.
"""
from __future__ import annotations

import logging
import re
from typing import Any, ClassVar

import httpx

from app.adapters.base import (
    BaseAdapter,
    Connection,
    DiskSpace,
    HealthIssue,
    HealthStatus,
    QueueItem,
)
from app.core.errors import ServiceUnavailable

log = logging.getLogger(__name__)

MASK = "********"  # what *arr apps return instead of a stored password / API key


# ---------------------------------------------------------------- generic helpers (all adapters)


def failed_status(exc: ServiceUnavailable, source: str | None = None) -> HealthStatus:
    """Turn a ServiceUnavailable into the `ping()` result that must be returned instead of raising."""
    return HealthStatus(
        ok=False,
        message=exc.message,
        issues=[HealthIssue(severity="error", message=exc.message, explanation=exc.explanation,
                            fix=exc.fix, source=source)],
    )


def parse_json(resp: httpx.Response, app_name: str) -> Any:
    """Decode a JSON body, or raise a friendly error (e.g. the port points at a web page, not the API)."""
    try:
        return resp.json()
    except ValueError as exc:
        raise ServiceUnavailable(
            f"{app_name} sent an answer Unifierr cannot read",
            explanation=f"The address answered, but not with {app_name}'s data. It may be the wrong port, "
                        "or a proxy login page.",
            fix=f"Check the address and port of {app_name} in Settings → Apps.",
        ) from exc


async def raw_request(adapter: BaseAdapter, method: str, path: str, **kw: Any) -> httpx.Response:
    """Like `BaseAdapter._request`, but only network failures raise: HTTP status codes are left to the caller."""
    name = adapter.display_name
    try:
        return await adapter.client.request(method, adapter._url(path), **kw)
    except httpx.ConnectError as exc:
        raise ServiceUnavailable(
            f"Cannot reach {name}",
            explanation=f"Unifierr could not open a connection to {name} at {adapter.conn.base_url}.",
            fix=f"Make sure {name} is running and that the address is correct.",
        ) from exc
    except httpx.TimeoutException as exc:
        raise ServiceUnavailable(
            f"{name} did not answer in time",
            explanation=f"{name} is reachable but too slow or stuck.",
            fix=f"Restart {name}. If it keeps happening, check its logs.",
        ) from exc
    except httpx.HTTPError as exc:
        raise ServiceUnavailable(f"Error talking to {name}: {exc.__class__.__name__}") from exc


def norm_path(p: str) -> str:
    """Compare-friendly path: forward slashes, no trailing slash, case-insensitive for Windows drives."""
    p = p.strip().replace("\\", "/")
    while len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p


def poster_from_images(images: list[dict[str, Any]] | None) -> str | None:
    """remoteUrl of the 'poster' image, only if it is an absolute https URL (never an internal URL)."""
    for img in images or []:
        if str(img.get("coverType", "")).lower() == "poster":
            url = img.get("remoteUrl")
            if isinstance(url, str) and url.startswith("https://"):
                return url
    return None


_TIMELEFT = re.compile(r"^(?:(\d+)\.)?(\d+):(\d+):(\d+)")


def parse_timeleft(value: str | None) -> int | None:
    """'1.02:03:04' / '00:12:34' (.NET TimeSpan) → seconds."""
    if not value:
        return None
    m = _TIMELEFT.match(value)
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


# ---------------------------------------------------------------- health translations

# source (the *arr "check" class name) -> (explanation, fix)
HEALTH_HELP: dict[str, tuple[str, str]] = {
    "IndexerStatusCheck": (
        "Some indexers (the sites that are searched for downloads) failed recently, so they are paused for a while.",
        "Usually temporary. Open Indexers in Unifierr and run a test; remove or replace indexers that keep failing.",
    ),
    "IndexerLongTermStatusCheck": (
        "Some indexers have been failing for a long time and were switched off.",
        "Test them in Indexers. If they still fail, the site may be down or blocked: replace them with another one.",
    ),
    "IndexerRssCheck": (
        "No indexer is set up for automatic new-release checks, so new releases will not be grabbed on their own.",
        "Add at least one working indexer (Indexers → Add), or turn RSS back on for an existing one.",
    ),
    "IndexerSearchCheck": (
        "No indexer is available for searching, so requested movies and shows cannot be found.",
        "Add at least one working indexer (Indexers → Add), or turn searching back on for an existing one.",
    ),
    "IndexerJackettAllCheck": (
        "An indexer uses Jackett's 'all' endpoint, which is not supported.",
        "Use Prowlarr (through Unifierr) to manage indexers instead.",
    ),
    "DownloadClientCheck": (
        "No download program (like qBittorrent) is connected, so nothing can be downloaded.",
        "Run 'Connect everything' in Unifierr, or add qBittorrent under Settings → Apps.",
    ),
    "DownloadClientStatusCheck": (
        "The download program (like qBittorrent) could not be reached recently.",
        "Make sure qBittorrent is running and its username and password are right, then run 'Connect everything'.",
    ),
    "DownloadClientRootFolderCheck": (
        "The download program puts files inside your media folder.",
        "Give downloads their own folder (for example /data/torrents) separate from /data/media.",
    ),
    "DownloadClientSortingCheck": (
        "The download program sorts files into folders on its own, which stops imports from working.",
        "Turn off sorting (like 'TV Sorting') in the download program.",
    ),
    "RootFolderCheck": (
        "The folder where media is stored is missing or not reachable.",
        "Make sure the folder exists and is mounted into the container, then run 'Connect everything'.",
    ),
    "ImportMechanismCheck": (
        "Finished downloads will not be moved into your library automatically.",
        "In the app's Settings → Media Management turn on 'Completed Download Handling'.",
    ),
    "RemotePathMappingCheck": (
        "The app and the download program see the same folder under different names, so finished files are not found.",
        "Use the same /data folder in both containers (Unifierr does this by default). If you changed "
        "folders, make them match again.",
    ),
    "UpdateCheck": (
        "The app cannot install its own update, usually because its program folder is read-only.",
        "Update the container image instead (Unifierr → Apps → Update).",
    ),
    "UpdateCheckStartupFolderCheck": (
        "The app cannot update itself from its start-up folder.",
        "Update the container image instead (Unifierr → Apps → Update).",
    ),
    "DiskSpaceCheck": (
        "A drive used for media is nearly full.",
        "Free some space or point the app at a bigger drive.",
    ),
    "MediaInfoDllCheck": (
        "A helper library for reading video files is missing.",
        "Pull the latest container image; this is normally included.",
    ),
    "ProxyCheck": (
        "The proxy configured in the app does not work.",
        "Fix or remove the proxy in the app's Settings → General.",
    ),
    "SystemTimeCheck": (
        "The clock of this computer is wrong, which can break logins and scheduling.",
        "Turn on automatic time on the host computer.",
    ),
    "ApplicationUrlCheck": (
        "The app does not know its own web address, which some links need.",
        "Optional: set the URL in the app's Settings → General.",
    ),
    "NotificationStatusCheck": (
        "A notification connection (for example to Jellyfin or Plex) failed recently.",
        "Make sure Jellyfin/Plex is running, then run 'Connect everything' again.",
    ),
    "ImportListStatusCheck": (
        "A list used to add movies or shows automatically could not be loaded.",
        "Check the list in the app's Settings → Lists, or remove it.",
    ),
    "ApplicationStatusCheck": (
        "Prowlarr could not talk to Radarr or Sonarr to share indexers.",
        "Make sure Radarr and Sonarr are running, then run 'Connect everything' again.",
    ),
    "ApplicationLongTermStatusCheck": (
        "Prowlarr has not been able to talk to Radarr or Sonarr for a long time.",
        "Make sure Radarr and Sonarr are running, then run 'Connect everything' again.",
    ),
    "IndexerProxyStatusCheck": (
        "A proxy used by indexers (like FlareSolverr) is not working.",
        "Check that the proxy container is running, or remove the proxy from the indexer.",
    ),
}


def _readable_health_message(item: dict[str, Any]) -> str:
    """The app's message, or (when the app sends an untranslated key like 'IndexerRssHealthCheckNoIndexers')
    the sentence hidden in its wiki link: '#no-indexers-available-...' -> 'No indexers available ...'."""
    message = str(item.get("message") or "").strip()
    if message and " " in message:
        return message
    anchor = str(item.get("wikiUrl") or "").partition("#")[2]
    if anchor:
        text = anchor.replace("-", " ").strip()
        return text[:1].upper() + text[1:]
    return message or str(item.get("source") or "Unknown problem")


def translate_health(items: Any, source: str) -> list[HealthIssue]:
    """Convert an *arr `/health` payload into beginner-friendly HealthIssue objects."""
    issues: list[HealthIssue] = []
    if not isinstance(items, list):
        return issues
    for it in items:
        if not isinstance(it, dict):
            continue
        kind = str(it.get("type", "warning")).lower()
        if kind == "ok":
            continue
        severity = "error" if kind == "error" else "info" if kind == "notice" else "warning"
        message = _readable_health_message(it)
        explanation, fix = HEALTH_HELP.get(str(it.get("source", "")), (None, None))
        issues.append(HealthIssue(severity=severity, message=message, explanation=explanation, fix=fix,  # type: ignore[arg-type]
                                  source=source))
    return issues


# ---------------------------------------------------------------- field helpers for schema-driven POSTs


def merge_fields(fields: list[dict[str, Any]], values: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """Set `values` (by field name) on a copy of an *arr `fields` list.

    Names the app does not know are ignored. Returns (new_fields, changed). *arr never gives
    secrets back (it shows '********'), so they cannot be compared: we always send our current
    value and count it as a change. Otherwise a reinstalled app's new API key would never be saved.
    """
    out: list[dict[str, Any]] = []
    changed = False
    for f in fields or []:
        f = dict(f)
        name = f.get("name")
        if name in values:
            new = values[name]
            old = f.get("value")
            if old == MASK:
                if new:
                    f["value"] = new
                    changed = True
            elif old != new:
                f["value"] = new
                changed = True
        out.append(f)
    return out, changed


def normalize_cf_spec_fields(fields: Any) -> list[dict[str, Any]]:
    """Convert TRaSH spec fields (`{"value": ...}` or `[{"name": "value", "value": ...}]`) to *arr API format."""
    if isinstance(fields, dict):
        return [{"name": str(k), "value": v} for k, v in fields.items()]
    if isinstance(fields, list):
        return [{"name": str(f.get("name", "")), "value": f.get("value")}
                for f in fields if isinstance(f, dict) and "name" in f]
    return []


def normalize_cf_payload(cf: dict[str, Any]) -> dict[str, Any]:
    """Build a clean *arr `/customformat` request body (stripping `trash_*` / `score` metadata)."""
    specs: list[dict[str, Any]] = []
    for s in cf.get("specifications") or []:
        specs.append({
            "name": str(s.get("name", "")),
            "implementation": str(s.get("implementation", "")),
            "negate": bool(s.get("negate", False)),
            "required": bool(s.get("required", False)),
            "fields": normalize_cf_spec_fields(s.get("fields")),
        })
    return {
        "name": str(cf["name"]),
        "includeCustomFormatWhenRenaming": bool(cf.get("includeCustomFormatWhenRenaming", False)),
        "specifications": specs,
    }


def _cf_signature(cf: dict[str, Any]) -> tuple[Any, ...]:
    norm = normalize_cf_payload(cf)
    spec_sigs = tuple(
        (
            s["name"],
            s["implementation"],
            s["negate"],
            s["required"],
            tuple(sorted((f["name"], repr(f.get("value"))) for f in s["fields"])),
        )
        for s in norm["specifications"]
    )
    return (norm["name"].strip().lower(), norm["includeCustomFormatWhenRenaming"], spec_sigs)


def _profile_items_signature(items: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    sig: list[tuple[Any, ...]] = []
    for it in items or []:
        q = it.get("quality") or {}
        sub = tuple((s.get("quality") or {}).get("name") or s.get("name") for s in (it.get("items") or []))
        sig.append((q.get("name") or it.get("name"), bool(it.get("allowed", False)), sub))
    return sig


def _profile_matches(existing: dict[str, Any], desired: dict[str, Any]) -> bool:
    for key in ("upgradeAllowed", "cutoff", "minFormatScore", "cutoffFormatScore", "minUpgradeFormatScore"):
        if key in desired and existing.get(key) != desired.get(key):
            return False
    if "items" in desired:
        if _profile_items_signature(existing.get("items") or []) != _profile_items_signature(desired["items"]):
            return False
    if "formatItems" in desired:
        ex_scores = {
            int(f["format"]): int(f.get("score", 0))
            for f in (existing.get("formatItems") or [])
            if isinstance(f, dict) and f.get("format") is not None
        }
        des_scores = {
            int(f["format"]): int(f.get("score", 0))
            for f in (desired.get("formatItems") or [])
            if isinstance(f, dict) and f.get("format") is not None
        }
        if ex_scores != des_scores:
            return False
    return True


# ---------------------------------------------------------------- base classes


class ArrBase(BaseAdapter):
    """Common bits of every v1/v3 *arr API: header auth, /system/status, /health, schema-driven ensure."""

    api_prefix: ClassVar[str] = "/api/v3"
    app_label: ClassVar[str] = "arr"  # used as HealthIssue.source

    def __init__(self, conn: Connection, client: httpx.AsyncClient | None = None):
        super().__init__(conn, client)
        self._headers = {"X-Api-Key": conn.api_key or "", "Accept": "application/json"}

    # ---- http ----
    async def _api(self, method: str, path: str, **kw: Any) -> httpx.Response:
        headers = {**self._headers, **kw.pop("headers", {})}
        return await self._request(method, f"{self.api_prefix}{path}", headers=headers, **kw)

    async def _json(self, method: str, path: str, **kw: Any) -> Any:
        return parse_json(await self._api(method, path, **kw), self.display_name)

    # ---- BaseAdapter ----
    async def ping(self) -> HealthStatus:
        try:
            data = await self._json("GET", "/system/status")
        except ServiceUnavailable as exc:
            return failed_status(exc, self.app_label)
        version = data.get("version") if isinstance(data, dict) else None
        return HealthStatus(ok=True, version=version, message="Connected")

    async def api_key_valid(self) -> bool:
        try:
            await self._api("GET", "/system/status")
        except ServiceUnavailable:
            return False
        return True

    async def health_issues(self) -> list[HealthIssue]:
        return translate_health(await self._json("GET", "/health"), self.app_label)

    async def set_ui_login(self, username: str, password: str) -> None:
        """Require a login for the app's own web page (forms auth) with the given credentials.

        Unifierr keeps using the API key, which is not affected."""
        host = await self._json("GET", "/config/host")
        host.update({
            "authenticationMethod": "forms",
            "authenticationRequired": "enabled",
            "username": username,
            "password": password,
            "passwordConfirmation": password,
        })
        await self._api("PUT", f"/config/host/{host.get('id', 1)}", json=host)

    # ---- schema-driven idempotent create/update ----
    async def _ensure_provider(
        self,
        resource: str,
        *,
        implementation: str,
        match_field: str,
        match_value: str,
        values: dict[str, Any],
        top: dict[str, Any],
        flags_true: frozenset[str] = frozenset(),
        match_norm: Any = lambda v: str(v).strip().rstrip("/").lower(),
    ) -> dict[str, Any]:
        """Find existing by implementation + `match_field` == `match_value`; update or create.

        Fallback: an entry with the same implementation AND the same name (e.g. Radarr was reinstalled and
        now has a new address or key) is updated instead of adding a duplicate, which the app would refuse."""
        existing = [e for e in (await self._json("GET", f"/{resource}") or [])
                    if e.get("implementation") == implementation]

        def value_of(entry: dict[str, Any]) -> Any:
            return next((f.get("value") for f in entry.get("fields", []) if f.get("name") == match_field), None)

        exact = next((e for e in existing if value_of(e) is not None
                      and match_norm(value_of(e)) == match_norm(match_value)), None)
        target = exact or next((e for e in existing if top.get("name") and e.get("name") == top["name"]), None)
        if target is not None:
            fields, changed = merge_fields(target.get("fields", []), values)
            if exact is not None and not changed:
                return target
            body = {**target, "fields": fields}
            resp = await self._api("PUT", f"/{resource}/{target['id']}", params={"forceSave": "true"}, json=body)
            return parse_json(resp, self.display_name)

        schemas = await self._json("GET", f"/{resource}/schema")
        schema = next((s for s in schemas or [] if s.get("implementation") == implementation), None)
        if schema is None:
            raise ServiceUnavailable(
                f"{self.display_name} does not support {implementation}",
                explanation=f"{self.display_name} does not list '{implementation}' as an option for {resource}.",
                fix=f"Update {self.display_name} to the latest version.",
            )
        fields, _ = merge_fields(schema.get("fields", []), values)
        body = {k: v for k, v in schema.items() if k != "id"}
        body["fields"] = fields
        body.update(top)
        for flag in flags_true:
            support = "supports" + flag[0].upper() + flag[1:]
            if flag in body and schema.get(support, True) is not False:
                body[flag] = True
        resp = await self._api("POST", f"/{resource}", params={"forceSave": "true"}, json=body)
        return parse_json(resp, self.display_name)


_NOTIFY_FLAGS = frozenset({
    "onDownload", "onUpgrade", "onRename",
    "onMovieDelete", "onMovieFileDelete", "onMovieFileDeleteForUpgrade",
    "onSeriesDelete", "onEpisodeFileDelete", "onEpisodeFileDeleteForUpgrade",
})


class ArrAdapter(ArrBase):
    """Radarr/Sonarr shared part (API v3). Subclasses set the media-specific bits."""

    qbit_category_field: ClassVar[str] = "movieCategory"
    queue_params: ClassVar[dict[str, str]] = {}
    queue_media_type: ClassVar[str] = "movie"
    queue_source: ClassVar[str] = "radarr"
    queue_media_key: ClassVar[str] = "movie"

    # ---- lookups & quality / custom format management common to both ----
    async def quality_profiles(self) -> list[dict[str, Any]]:
        data = await self._json("GET", "/qualityprofile")
        return [{**p, "id": p["id"], "name": p.get("name", "")} for p in data or []]

    async def quality_profile_schema(self) -> dict[str, Any]:
        try:
            data = await self._json("GET", "/qualityprofile/schema")
        except ServiceUnavailable:
            return {}
        return data if isinstance(data, dict) else {}

    async def create_quality_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        body = {k: v for k, v in profile.items() if k != "id"}
        resp = await self._api("POST", "/qualityprofile", json=body)
        return parse_json(resp, self.display_name)

    async def update_quality_profile(self, profile_id: int, profile: dict[str, Any]) -> dict[str, Any]:
        body = {**profile, "id": int(profile_id)}
        resp = await self._api("PUT", f"/qualityprofile/{int(profile_id)}", json=body)
        return parse_json(resp, self.display_name)

    async def ensure_quality_profile(
        self, profile: dict[str, Any], *, existing: list[dict[str, Any]] | None = None
    ) -> tuple[dict[str, Any], str]:
        """Idempotently create or update a quality profile by name. Never deletes user profiles."""
        profiles = existing if existing is not None else await self.quality_profiles()
        target_name = str(profile.get("name", "")).strip().lower()
        match = next((p for p in profiles if str(p.get("name", "")).strip().lower() == target_name), None)
        if match is None:
            created = await self.create_quality_profile(profile)
            return created, "created"
        if _profile_matches(match, profile):
            return match, "unchanged"
        merged = {**match, **profile, "id": int(match["id"])}
        updated = await self.update_quality_profile(int(match["id"]), merged)
        return updated, "updated"

    async def custom_formats(self) -> list[dict[str, Any]]:
        data = await self._json("GET", "/customformat")
        return list(data or [])

    async def create_custom_format(self, custom_format: dict[str, Any]) -> dict[str, Any]:
        payload = normalize_cf_payload(custom_format)
        resp = await self._api("POST", "/customformat", json=payload)
        return parse_json(resp, self.display_name)

    async def update_custom_format(self, custom_format_id: int, custom_format: dict[str, Any]) -> dict[str, Any]:
        payload = {**normalize_cf_payload(custom_format), "id": int(custom_format_id)}
        resp = await self._api("PUT", f"/customformat/{int(custom_format_id)}", json=payload)
        return parse_json(resp, self.display_name)

    async def ensure_custom_format(
        self, custom_format: dict[str, Any], *, existing: list[dict[str, Any]] | None = None
    ) -> tuple[dict[str, Any], str]:
        """Idempotently create or update a custom format by name."""
        formats = existing if existing is not None else await self.custom_formats()
        target_name = str(custom_format.get("name", "")).strip().lower()
        match = next((f for f in formats if str(f.get("name", "")).strip().lower() == target_name), None)
        if match is None:
            created = await self.create_custom_format(custom_format)
            return created, "created"
        if _cf_signature(match) == _cf_signature(custom_format):
            return match, "unchanged"
        updated = await self.update_custom_format(int(match["id"]), {**match, **normalize_cf_payload(custom_format)})
        return updated, "updated"

    async def quality_definitions(self) -> list[dict[str, Any]]:
        data = await self._json("GET", "/qualitydefinition")
        return list(data or [])

    async def update_quality_definition(self, definition_id: int, definition: dict[str, Any]) -> dict[str, Any]:
        body = {**definition, "id": int(definition_id)}
        resp = await self._api("PUT", f"/qualitydefinition/{int(definition_id)}", json=body)
        return parse_json(resp, self.display_name)

    async def update_quality_definitions(self, definitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        resp = await self._api("PUT", "/qualitydefinition/update", json=definitions)
        return list(parse_json(resp, self.display_name) or [])

    async def ensure_quality_definitions(self, definitions: list[dict[str, Any]]) -> dict[str, list[str]]:
        """Idempotently apply TRaSH quality size limits (`min`, `preferred`, `max`)."""
        existing = await self.quality_definitions()
        by_name: dict[str, dict[str, Any]] = {}
        for d in existing:
            q_name = str((d.get("quality") or {}).get("name") or d.get("title") or "").strip().lower()
            if q_name:
                by_name[q_name] = d

        updated_names: list[str] = []
        unchanged_names: list[str] = []
        for item in definitions or []:
            q_label = str(item.get("quality") or item.get("title") or "").strip()
            target = by_name.get(q_label.lower())
            if target is None or target.get("id") is None:
                continue
            new_min = float(item.get("min", item.get("minSize", target.get("minSize", 0.0))))
            new_max = float(item.get("max", item.get("maxSize", target.get("maxSize", 0.0))))
            new_pref = float(item.get("preferred", item.get("preferredSize", target.get("preferredSize", new_max))))
            cur_min = float(target.get("minSize") or 0.0)
            cur_max = float(target.get("maxSize") or 0.0)
            cur_pref = float(target.get("preferredSize") if target.get("preferredSize") is not None else new_pref)
            if abs(cur_min - new_min) < 1e-3 and abs(cur_max - new_max) < 1e-3 and abs(cur_pref - new_pref) < 1e-3:
                unchanged_names.append(q_label)
                continue
            body = {**target, "minSize": new_min, "maxSize": new_max, "preferredSize": new_pref}
            await self.update_quality_definition(int(target["id"]), body)
            updated_names.append(q_label)
        return {"updated": updated_names, "unchanged": unchanged_names}

    async def root_folders(self) -> list[dict[str, Any]]:
        data = await self._json("GET", "/rootfolder")
        return [{"id": r.get("id"), "path": r.get("path"), "freeSpace": r.get("freeSpace"),
                 "accessible": r.get("accessible", True)} for r in data or []]

    async def ensure_root_folder(self, path: str) -> dict[str, Any]:
        for r in await self._json("GET", "/rootfolder") or []:
            if norm_path(str(r.get("path", ""))) == norm_path(path):
                return r
        resp = await self._api("POST", "/rootfolder", json={"path": path})
        return parse_json(resp, self.display_name)

    async def disk_space(self) -> list[DiskSpace]:
        out: list[DiskSpace] = []
        for d in await self._json("GET", "/diskspace") or []:
            out.append(DiskSpace(path=str(d.get("path", "")), label=d.get("label") or None,
                                 free_bytes=int(d.get("freeSpace") or 0), total_bytes=int(d.get("totalSpace") or 0)))
        return out

    async def _default_root_and_profile(
        self, root_folder: str | None, quality_profile_id: int | None
    ) -> tuple[str, int]:
        if root_folder is None:
            roots = await self.root_folders()
            if not roots:
                raise ServiceUnavailable(
                    f"{self.display_name} has no media folder yet",
                    explanation=f"{self.display_name} needs a root folder before anything can be added.",
                    fix="Run 'Connect everything' in Unifierr, or add a root folder in the app.",
                )
            root_folder = str(roots[0]["path"])
        if quality_profile_id is None:
            profiles = await self.quality_profiles()
            if not profiles:
                raise ServiceUnavailable(
                    f"{self.display_name} has no quality profile",
                    explanation="A quality profile tells the app which release quality to download.",
                    fix=f"Create a quality profile in {self.display_name} → Settings → Profiles.",
                )
            quality_profile_id = int(profiles[0]["id"])
        return root_folder, quality_profile_id

    # ---- download client / notification ----
    async def ensure_qbittorrent_client(self, *, host: str, port: int, username: str, password: str,
                                        category: str | None = None, use_ssl: bool = False) -> dict[str, Any]:
        category = category or ("radarr" if self.qbit_category_field == "movieCategory" else "tv-sonarr")
        values = {"host": host, "port": int(port), "useSsl": use_ssl, "username": username, "password": password,
                  self.qbit_category_field: category}
        return await self._ensure_provider(
            "downloadclient", implementation="QBittorrent", match_field="host", match_value=host, values=values,
            top={"name": "qBittorrent", "enable": True, "priority": 1, "protocol": "torrent", "tags": []},
        )

    async def ensure_media_server_notification(self, *, kind: str, host: str, port: int, api_key: str,
                                               use_ssl: bool = False) -> dict[str, Any]:
        kind = str(kind).lower()
        if kind == "plex":
            implementation, name = "PlexServer", "Plex"
            values: dict[str, Any] = {"host": host, "port": int(port), "useSsl": use_ssl, "authToken": api_key,
                                      "updateLibrary": True}
        elif kind in ("jellyfin", "emby"):
            implementation, name = "MediaBrowser", "Jellyfin"
            values = {"host": host, "port": int(port), "useSsl": use_ssl, "apiKey": api_key,
                      "updateLibrary": True}
        else:
            raise ServiceUnavailable(f"Unsupported media server: {kind}")
        return await self._ensure_provider(
            "notification", implementation=implementation, match_field="host", match_value=host, values=values,
            top={"name": name, "tags": []}, flags_true=_NOTIFY_FLAGS,
        )

    # ---- queue ----
    async def queue(self) -> list[QueueItem]:
        data = await self._json("GET", "/queue", params={**self.queue_params, "pageSize": "200"})
        records = data.get("records", []) if isinstance(data, dict) else data
        return [self._queue_item(r) for r in records or []]

    def _queue_item(self, r: dict[str, Any]) -> QueueItem:
        size = int(r.get("size") or 0)
        left = int(r.get("sizeleft") or 0)
        progress = round((size - left) / size * 100, 1) if size > 0 else 0.0
        tracked = str(r.get("trackedDownloadState") or "")
        tstatus = str(r.get("trackedDownloadStatus") or "").lower()
        status = str(r.get("status") or "").lower()
        error = self._queue_error(r)
        if tracked in ("importPending", "importing"):
            state = "importing"
        elif tstatus == "error" or status == "failed" or tracked in ("importBlocked", "importFailed", "failed",
                                                                      "failedPending"):
            state = "error"
            error = error or "The download failed or could not be imported."
        else:
            state = {"downloading": "downloading", "paused": "paused", "queued": "queued", "delay": "queued",
                     "completed": "completed", "warning": "downloading"}.get(status, "unknown")
        download_id = r.get("downloadId")
        media = r.get(self.queue_media_key) or {}
        return QueueItem(
            id=str(download_id).lower() if download_id else f"{self.queue_source}:{r.get('id')}",
            name=str(r.get("title") or media.get("title") or "Unknown"),
            source=self.queue_source,  # type: ignore[arg-type]
            state=state,  # type: ignore[arg-type]
            progress=max(0.0, min(100.0, progress)),
            size=size or None,
            downloaded=max(size - left, 0) if size else None,
            eta_seconds=parse_timeleft(r.get("timeleft")),
            media_title=media.get("title"),
            media_type=self.queue_media_type,  # type: ignore[arg-type]
            error=error,
        )

    @staticmethod
    def _queue_error(r: dict[str, Any]) -> str | None:
        parts: list[str] = []
        for sm in r.get("statusMessages") or []:
            msgs = sm.get("messages") or ([sm["title"]] if sm.get("title") else [])
            parts.extend(str(m) for m in msgs)
        if not parts and r.get("errorMessage"):
            parts.append(str(r["errorMessage"]))
        return "; ".join(parts) or None
