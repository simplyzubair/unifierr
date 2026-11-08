"""Sync TRaSH-Guides quality definitions, custom formats, and quality profiles into Radarr and Sonarr.

All TRaSH JSON definitions are fetched live from the upstream TRaSH-Guides repository
(`https://raw.githubusercontent.com/TRaSH-Guides/Guides/master/docs/json/`) via httpx with a timeout.
Never deletes user profiles; only creates or updates the TRaSH-named custom formats and quality profiles.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters._arr_common import ArrAdapter, normalize_cf_spec_fields
from app.adapters.base import ServiceKind
from app.core.db import sessionmaker
from app.core.errors import ServiceUnavailable, UnifierrError
from app.services.common import adapter_for, get_service, get_setting, log_event, set_settings
from app.services.jobs import Job

log = logging.getLogger("unifierr.trash")

TRASH_BASE_URL = "https://raw.githubusercontent.com/TRaSH-Guides/Guides/master/docs/json"
DEFAULT_TRASH_PROFILE = "hd-1080p"
TRASH_TIMEOUT = 15.0


@dataclass(frozen=True, slots=True)
class TrashPreset:
    id: str
    name: str
    description: str
    radarr_slug: str
    radarr_profile: str
    sonarr_slug: str
    sonarr_profile: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "radarr_slug": self.radarr_slug,
            "radarr_profile": self.radarr_profile,
            "sonarr_slug": self.sonarr_slug,
            "sonarr_profile": self.sonarr_profile,
        }


TRASH_PRESETS: dict[str, TrashPreset] = {
    "hd-1080p": TrashPreset(
        id="hd-1080p",
        name="1080p HD (Bluray + WEB)",
        description="Best 1080p Blu-ray and WEB-DL releases, blocking low-quality encodes, CAMs, and full discs.",
        radarr_slug="hd-bluray-web",
        radarr_profile="HD Bluray + WEB",
        sonarr_slug="web-1080p",
        sonarr_profile="WEB-1080p",
    ),
    "uhd-2160p": TrashPreset(
        id="uhd-2160p",
        name="4K UHD (Bluray + WEB)",
        description="High-bitrate 2160p 4K Blu-ray and WEB-DL releases with TRaSH release group tiers.",
        radarr_slug="uhd-bluray-web",
        radarr_profile="UHD Bluray + WEB",
        sonarr_slug="web-2160p",
        sonarr_profile="WEB-2160p",
    ),
    "remux-1080p": TrashPreset(
        id="remux-1080p",
        name="1080p Remux + WEB (Lossless HD)",
        description="Untouched lossless 1080p Blu-ray Remuxes and top-tier 1080p WEB-DL releases.",
        radarr_slug="remux-web-1080p",
        radarr_profile="Remux + WEB 1080p",
        sonarr_slug="remux-web-1080p",
        sonarr_profile="Remux + WEB 1080p",
    ),
    "remux-2160p": TrashPreset(
        id="remux-2160p",
        name="4K Remux + WEB (Lossless 4K)",
        description="Untouched lossless 2160p UHD Blu-ray Remuxes and top-tier 4K WEB-DL releases.",
        radarr_slug="remux-web-2160p",
        radarr_profile="Remux + WEB 2160p",
        sonarr_slug="remux-web-2160p",
        sonarr_profile="Remux + WEB 2160p",
    ),
    "web-1080p": TrashPreset(
        id="web-1080p",
        name="1080p WEB Only (Compact)",
        description="Streaming 1080p WEB-DL releases only for smaller file sizes and fast downloads.",
        radarr_slug="web-1080p",
        radarr_profile="WEB 1080p",
        sonarr_slug="web-1080p",
        sonarr_profile="WEB-1080p",
    ),
    "web-2160p": TrashPreset(
        id="web-2160p",
        name="4K WEB Only",
        description="Streaming 2160p 4K WEB-DL releases only.",
        radarr_slug="web-2160p",
        radarr_profile="WEB 2160p",
        sonarr_slug="web-2160p",
        sonarr_profile="WEB-2160p",
    ),
}

# Standard *arr quality IDs used when an instance returns minimal profile payloads without schema metadata.
_RADARR_QUALITIES: list[ tuple[int, str, str, int] ] = [
    (0, "Unknown", "unknown", 0),
    (24, "WORKPRINT", "workprint", 0),
    (25, "CAM", "cam", 0),
    (26, "TELESYNC", "telesync", 0),
    (27, "TELECINE", "telecine", 0),
    (29, "REGIONAL", "dvd", 480),
    (28, "DVDSCR", "dvd", 480),
    (1, "SDTV", "tv", 480),
    (2, "DVD", "dvd", 480),
    (23, "DVD-R", "dvd", 480),
    (8, "WEBDL-480p", "web", 480),
    (12, "WEBRip-480p", "webRip", 480),
    (20, "Bluray-480p", "bluray", 480),
    (21, "Bluray-576p", "bluray", 576),
    (4, "HDTV-720p", "tv", 720),
    (5, "WEBDL-720p", "web", 720),
    (14, "WEBRip-720p", "webRip", 720),
    (6, "Bluray-720p", "bluray", 720),
    (9, "HDTV-1080p", "tv", 1080),
    (3, "WEBDL-1080p", "web", 1080),
    (15, "WEBRip-1080p", "webRip", 1080),
    (7, "Bluray-1080p", "bluray", 1080),
    (30, "Remux-1080p", "bluray", 1080),
    (16, "HDTV-2160p", "tv", 2160),
    (18, "WEBDL-2160p", "web", 2160),
    (17, "WEBRip-2160p", "webRip", 2160),
    (19, "Bluray-2160p", "bluray", 2160),
    (31, "Remux-2160p", "bluray", 2160),
    (22, "BR-DISK", "bluray", 1080),
    (10, "Raw-HD", "tv", 1080),
]

_SONARR_QUALITIES: list[ tuple[int, str, str, int] ] = [
    (0, "Unknown", "unknown", 0),
    (1, "SDTV", "television", 480),
    (8, "WEBDL-480p", "web", 480),
    (12, "WEBRip-480p", "webRip", 480),
    (2, "DVD", "dvd", 480),
    (22, "Bluray-480p", "bluray", 480),
    (23, "Bluray-576p", "bluray", 576),
    (4, "HDTV-720p", "television", 720),
    (9, "HDTV-1080p", "television", 1080),
    (10, "Raw-HD", "televisionRaw", 1080),
    (5, "WEBDL-720p", "web", 720),
    (14, "WEBRip-720p", "webRip", 720),
    (6, "Bluray-720p", "bluray", 720),
    (3, "WEBDL-1080p", "web", 1080),
    (15, "WEBRip-1080p", "webRip", 1080),
    (7, "Bluray-1080p", "bluray", 1080),
    (20, "Bluray-1080p Remux", "blurayRaw", 1080),
    (16, "HDTV-2160p", "television", 2160),
    (18, "WEBDL-2160p", "web", 2160),
    (17, "WEBRip-2160p", "webRip", 2160),
    (19, "Bluray-2160p", "bluray", 2160),
    (21, "Bluray-2160p Remux", "blurayRaw", 2160),
]


@dataclass(slots=True)
class TrashBundle:
    kind: ServiceKind
    profile_slug: str
    quality_definitions: list[dict[str, Any]]
    custom_formats: list[dict[str, Any]]
    raw_profile: dict[str, Any]
    score_overrides: dict[str, int] = field(default_factory=dict)


def cf_slug(name: str) -> str:
    """Map a TRaSH Custom Format display name (e.g. 'Repack/Proper', 'LQ (Release Title)') to its JSON filename slug."""
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")


def normalize_preset_key(choice: str | None) -> str:
    """Normalize a preset id, profile slug, or display name to a canonical preset key when possible."""
    if not choice:
        return DEFAULT_TRASH_PROFILE
    cleaned = str(choice).strip()
    lower = cleaned.lower()
    if lower in TRASH_PRESETS:
        return lower
    for key, preset in TRASH_PRESETS.items():
        if lower in (
            preset.name.lower(),
            preset.radarr_slug.lower(),
            preset.sonarr_slug.lower(),
            preset.radarr_profile.lower(),
            preset.sonarr_profile.lower(),
        ):
            return key
    return cf_slug(cleaned) or DEFAULT_TRASH_PROFILE


def resolve_profile_slug(kind: ServiceKind, choice: str | None = None) -> str:
    """Resolve the upstream TRaSH quality-profiles JSON slug for `kind` (`radarr` or `sonarr`)."""
    if not choice:
        choice = DEFAULT_TRASH_PROFILE
    cleaned = str(choice).strip()
    lower = cleaned.lower()
    if lower in TRASH_PRESETS:
        preset = TRASH_PRESETS[lower]
        return preset.radarr_slug if kind == ServiceKind.radarr else preset.sonarr_slug
    for preset in TRASH_PRESETS.values():
        if kind == ServiceKind.radarr and lower in (preset.radarr_slug.lower(), preset.radarr_profile.lower()):
            return preset.radarr_slug
        if kind == ServiceKind.sonarr and lower in (preset.sonarr_slug.lower(), preset.sonarr_profile.lower()):
            return preset.sonarr_slug
        if lower == preset.name.lower():
            return preset.radarr_slug if kind == ServiceKind.radarr else preset.sonarr_slug
    return cf_slug(cleaned)


def target_profile_name(kind: ServiceKind, choice: str | None = None) -> str:
    """Return the expected TRaSH quality profile display name in Radarr or Sonarr."""
    if not choice:
        choice = DEFAULT_TRASH_PROFILE
    cleaned = str(choice).strip()
    lower = cleaned.lower()
    if lower in TRASH_PRESETS:
        preset = TRASH_PRESETS[lower]
        return preset.radarr_profile if kind == ServiceKind.radarr else preset.sonarr_profile
    for preset in TRASH_PRESETS.values():
        if kind == ServiceKind.radarr and lower in (preset.radarr_slug.lower(), preset.radarr_profile.lower()):
            return preset.radarr_profile
        if kind == ServiceKind.sonarr and lower in (preset.sonarr_slug.lower(), preset.sonarr_profile.lower()):
            return preset.sonarr_profile
        if lower == preset.name.lower():
            return preset.radarr_profile if kind == ServiceKind.radarr else preset.sonarr_profile
    return cleaned


# ---------------------------------------------------------------- live HTTP fetching


async def fetch_trash_json(
    path: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Download a single JSON file from the public TRaSH-Guides repository."""
    url = path if path.startswith("https://") or path.startswith("http://") else f"{TRASH_BASE_URL}/{path.lstrip('/')}"
    own = client is None
    http = client or httpx.AsyncClient(timeout=TRASH_TIMEOUT, follow_redirects=True)
    try:
        try:
            resp = await http.get(url, headers={"Accept": "application/json"})
        except httpx.TimeoutException as exc:
            raise ServiceUnavailable(
                "TRaSH-Guides did not answer in time",
                explanation="Unifierr could not download quality profile definitions from GitHub before the timeout.",
                fix="Check your internet connection and click Apply TRaSH Profiles again.",
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceUnavailable(
                "Cannot reach TRaSH-Guides on GitHub",
                explanation="Unifierr could not connect to raw.githubusercontent.com to download TRaSH profiles.",
                fix="Make sure this server has internet access and DNS is working, then try again.",
            ) from exc

        if resp.status_code == 404:
            raise ServiceUnavailable(
                f"TRaSH-Guides definition not found ({path})",
                explanation=f"The requested TRaSH-Guides file '{path}' was not found upstream.",
                fix="Choose one of the standard TRaSH quality profiles and retry.",
            )
        if resp.status_code >= 400:
            raise ServiceUnavailable(
                f"TRaSH-Guides returned HTTP {resp.status_code}",
                explanation="GitHub returned an error while downloading TRaSH quality profile definitions.",
                fix="Wait a moment and retry applying TRaSH quality profiles.",
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise ServiceUnavailable(
                "TRaSH-Guides returned unreadable JSON",
                explanation=f"The response from {url} was not valid JSON.",
                fix="Check if a firewall or captive portal is intercepting requests to raw.githubusercontent.com.",
            ) from exc
        if not isinstance(data, dict):
            raise ServiceUnavailable(
                "TRaSH-Guides returned an unexpected JSON shape",
                explanation=f"Expected a JSON object from {path}.",
                fix="Retry or select a standard TRaSH profile.",
            )
        return data
    finally:
        if own:
            await http.aclose()


async def fetch_trash_bundle(
    kind: ServiceKind,
    profile_choice: str | None = DEFAULT_TRASH_PROFILE,
    *,
    client: httpx.AsyncClient | None = None,
    include_unwanted: bool = True,
) -> TrashBundle:
    """Download quality-size, quality-profile, and all referenced custom-format JSON blobs for `kind`."""
    if kind not in (ServiceKind.radarr, ServiceKind.sonarr):
        raise UnifierrError(f"TRaSH quality profiles only apply to Radarr and Sonarr (got {kind}).")

    app_dir = kind.value
    size_type = "movie" if kind == ServiceKind.radarr else "series"
    profile_slug = resolve_profile_slug(kind, profile_choice)

    own = client is None
    http = client or httpx.AsyncClient(timeout=TRASH_TIMEOUT, follow_redirects=True)
    try:
        raw_sizes, raw_profile = await asyncio.gather(
            fetch_trash_json(f"{app_dir}/quality-size/{size_type}.json", client=http),
            fetch_trash_json(f"{app_dir}/quality-profiles/{profile_slug}.json", client=http),
        )

        # Collect custom formats referenced by the profile's formatItems.
        cf_names: list[str] = []
        score_overrides: dict[str, int] = {}
        raw_format_items = raw_profile.get("formatItems") or {}
        if isinstance(raw_format_items, dict):
            for cf_name, val in raw_format_items.items():
                cf_names.append(str(cf_name))
                if isinstance(val, int) and not isinstance(val, bool):
                    score_overrides[str(cf_name).lower()] = val
                elif isinstance(val, dict) and isinstance(val.get("score"), int):
                    score_overrides[str(cf_name).lower()] = int(val["score"])
        elif isinstance(raw_format_items, list):
            for entry in raw_format_items:
                if isinstance(entry, dict) and entry.get("name"):
                    cf_names.append(str(entry["name"]))
                    if isinstance(entry.get("score"), int):
                        score_overrides[str(entry["name"]).lower()] = int(entry["score"])

        # Optionally include TRaSH's default unwanted custom formats (e.g. BR-DISK, LQ, Upscaled) when available.
        if include_unwanted:
            try:
                unwanted_group = await fetch_trash_json(
                    f"{app_dir}/cf-groups/unwanted-formats.json", client=http
                )
            except ServiceUnavailable:
                unwanted_group = {}
            included_profiles = ((unwanted_group.get("quality_profiles") or {}).get("include") or {})
            profile_trash_id = str(raw_profile.get("trash_id") or "")
            profile_name = str(raw_profile.get("name") or "")
            applies = (
                not included_profiles
                or profile_name in included_profiles
                or profile_trash_id in included_profiles.values()
            )
            if applies:
                seen_lower = {n.lower() for n in cf_names}
                for cf_entry in unwanted_group.get("custom_formats") or []:
                    if not isinstance(cf_entry, dict):
                        continue
                    if cf_entry.get("default") is True or cf_entry.get("required") is True:
                        u_name = str(cf_entry.get("name") or "").strip()
                        if u_name and u_name.lower() not in seen_lower:
                            cf_names.append(u_name)
                            seen_lower.add(u_name.lower())

        # Fetch all custom format JSON blobs concurrently.
        raw_cfs = await asyncio.gather(
            *(fetch_trash_json(f"{app_dir}/cf/{cf_slug(name)}.json", client=http) for name in cf_names)
        )
        score_set = str(raw_profile.get("trash_score_set") or "default")
        parsed_cfs = [
            parse_custom_format(
                raw_cf,
                score_override=score_overrides.get(str(raw_cf.get("name", "")).lower()),
                score_set=score_set,
            )
            for raw_cf in raw_cfs
        ]
        parsed_defs = parse_quality_definitions(raw_sizes)
        return TrashBundle(
            kind=kind,
            profile_slug=profile_slug,
            quality_definitions=parsed_defs,
            custom_formats=parsed_cfs,
            raw_profile=raw_profile,
            score_overrides=score_overrides,
        )
    finally:
        if own:
            await http.aclose()


# ---------------------------------------------------------------- pure parsing & mapping


def parse_quality_definitions(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse TRaSH `quality-size/*.json` into normalized `{quality, min, preferred, max}` dicts."""
    qualities = raw.get("qualities")
    if not isinstance(qualities, list):
        return []
    out: list[dict[str, Any]] = []
    for item in qualities:
        if not isinstance(item, dict) or not item.get("quality"):
            continue
        q_name = str(item["quality"]).strip()
        min_val = float(item.get("min", 0.0))
        max_val = float(item.get("max", 2000.0))
        pref_val = float(item.get("preferred", max_val))
        out.append({
            "quality": q_name,
            "min": min_val,
            "preferred": pref_val,
            "max": max_val,
        })
    return out


def parse_custom_format(
    raw: dict[str, Any],
    *,
    score_override: int | None = None,
    score_set: str = "default",
) -> dict[str, Any]:
    """Parse a TRaSH Custom Format JSON blob into a normalized dict with *arr-compatible specifications and score."""
    name = str(raw.get("name") or "").strip()
    if not name:
        raise ValueError("Custom format JSON is missing 'name'.")

    scores = raw.get("trash_scores") if isinstance(raw.get("trash_scores"), dict) else {}
    if score_override is not None:
        score = int(score_override)
    elif score_set in scores and scores[score_set] is not None:
        score = int(scores[score_set])
    elif "default" in scores and scores["default"] is not None:
        score = int(scores["default"])
    elif isinstance(raw.get("score"), (int, float)):
        score = int(raw["score"])
    else:
        score = 0

    specs: list[dict[str, Any]] = []
    for spec in raw.get("specifications") or []:
        if not isinstance(spec, dict):
            continue
        specs.append({
            "name": str(spec.get("name") or ""),
            "implementation": str(spec.get("implementation") or ""),
            "negate": bool(spec.get("negate", False)),
            "required": bool(spec.get("required", False)),
            "fields": normalize_cf_spec_fields(spec.get("fields")),
        })

    return {
        "trash_id": str(raw.get("trash_id") or ""),
        "name": name,
        "includeCustomFormatWhenRenaming": bool(raw.get("includeCustomFormatWhenRenaming", False)),
        "specifications": specs,
        "score": score,
    }


def _build_quality_catalog(
    kind: ServiceKind,
    existing_profiles: list[dict[str, Any]] | None = None,
    schema: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build a case-insensitive lookup `quality_name -> {id, name, source, resolution}`."""
    catalog: dict[str, dict[str, Any]] = {}
    defaults = _RADARR_QUALITIES if kind == ServiceKind.radarr else _SONARR_QUALITIES
    for q_id, q_name, source, res in defaults:
        catalog[q_name.lower()] = {"id": q_id, "name": q_name, "source": source, "resolution": res}

    sources: list[dict[str, Any]] = []
    if schema and isinstance(schema.get("items"), list):
        sources.append(schema)
    for prof in existing_profiles or []:
        if isinstance(prof, dict) and isinstance(prof.get("items"), list):
            sources.append(prof)

    for src in sources:
        for item in src.get("items") or []:
            if not isinstance(item, dict):
                continue
            q = item.get("quality")
            if isinstance(q, dict) and q.get("name") and q.get("id") is not None:
                catalog[str(q["name"]).lower()] = dict(q)
            for sub in item.get("items") or []:
                if isinstance(sub, dict):
                    sq = sub.get("quality")
                    if isinstance(sq, dict) and sq.get("name") and sq.get("id") is not None:
                        catalog[str(sq["name"]).lower()] = dict(sq)
    return catalog


def parse_quality_profile(
    raw_profile: dict[str, Any],
    custom_formats: list[dict[str, Any]],
    *,
    existing_profiles: list[dict[str, Any]] | None = None,
    schema: dict[str, Any] | None = None,
    all_arr_cfs: list[dict[str, Any]] | None = None,
    kind: ServiceKind = ServiceKind.radarr,
) -> dict[str, Any]:
    """Convert a TRaSH quality profile JSON + synced custom formats into a *arr `/qualityprofile` payload."""
    name = str(raw_profile.get("name") or "").strip()
    if not name:
        raise ValueError("Quality profile JSON is missing 'name'.")

    catalog = _build_quality_catalog(kind, existing_profiles, schema)
    used_qualities: set[str] = set()
    next_group_id = 1000
    group_ids_by_name: dict[str, int] = {}
    quality_ids_by_name: dict[str, int] = {v["name"].lower(): int(v["id"]) for v in catalog.values()}

    def resolve_quality(q_name: str) -> dict[str, Any]:
        key = q_name.strip().lower()
        used_qualities.add(key)
        if key in catalog:
            return catalog[key]
        new_id = max(quality_ids_by_name.values(), default=31) + 1
        q_obj = {"id": new_id, "name": q_name.strip(), "source": "unknown", "resolution": 0}
        catalog[key] = q_obj
        quality_ids_by_name[key] = new_id
        return q_obj

    # TRaSH lists items from highest priority (index 0) to lowest priority.
    # Radarr/Sonarr API v3 stores items from lowest priority to highest priority.
    trash_items_top_down: list[dict[str, Any]] = []
    for raw_item in raw_profile.get("items") or []:
        if not isinstance(raw_item, dict) or not raw_item.get("name"):
            continue
        item_name = str(raw_item["name"]).strip()
        allowed = bool(raw_item.get("allowed", False))
        sub_names = raw_item.get("items")
        if isinstance(sub_names, list) and sub_names:
            group_id = next_group_id
            next_group_id += 1
            group_ids_by_name[item_name.lower()] = group_id
            sub_items = []
            for sub in sub_names:
                sub_q_name = str(sub.get("name") if isinstance(sub, dict) else sub).strip()
                sub_items.append({
                    "quality": resolve_quality(sub_q_name),
                    "items": [],
                    "allowed": allowed,
                })
            trash_items_top_down.append({
                "id": group_id,
                "name": item_name,
                "items": sub_items,
                "allowed": allowed,
            })
        else:
            q_obj = resolve_quality(item_name)
            trash_items_top_down.append({
                "quality": q_obj,
                "items": [],
                "allowed": allowed,
            })

    # Include any qualities from the server's schema/existing profiles not explicitly listed in TRaSH JSON
    # as disallowed at the bottom so Radarr/Sonarr validation ("must contain all qualities") always succeeds.
    extra_bottom: list[dict[str, Any]] = []
    if schema or existing_profiles:
        known_from_server: list[dict[str, Any]] = []
        for src in ([schema] if schema else []) + list(existing_profiles or []):
            if not isinstance(src, dict):
                continue
            for it in src.get("items") or []:
                if not isinstance(it, dict):
                    continue
                if isinstance(it.get("quality"), dict):
                    known_from_server.append(it["quality"])
                for sub in it.get("items") or []:
                    if isinstance(sub, dict) and isinstance(sub.get("quality"), dict):
                        known_from_server.append(sub["quality"])
        for q_obj in known_from_server:
            q_key = str(q_obj.get("name", "")).strip().lower()
            if q_key and q_key not in used_qualities:
                used_qualities.add(q_key)
                extra_bottom.append({"quality": dict(q_obj), "items": [], "allowed": False})

    arr_items = extra_bottom + list(reversed(trash_items_top_down))

    # Resolve cutoff integer ID (either a group ID like 1000 or a quality ID like 7).
    cutoff_raw = raw_profile.get("cutoff")
    cutoff_id: int | None = None
    if isinstance(cutoff_raw, int):
        cutoff_id = cutoff_raw
    elif isinstance(cutoff_raw, str) and cutoff_raw.strip():
        c_key = cutoff_raw.strip().lower()
        if c_key in group_ids_by_name:
            cutoff_id = group_ids_by_name[c_key]
        elif c_key in quality_ids_by_name:
            cutoff_id = quality_ids_by_name[c_key]
    if cutoff_id is None:
        # Fallback: highest allowed item in the profile
        for it in trash_items_top_down:
            if it.get("allowed"):
                cutoff_id = int(it["id"] if "id" in it else it["quality"]["id"])
                break
        if cutoff_id is None:
            cutoff_id = 1

    # Map custom formats and their scores into formatItems.
    score_by_name: dict[str, int] = {}
    score_by_trash_id: dict[str, int] = {}
    cf_id_by_name: dict[str, int] = {}
    cf_name_canonical: dict[str, str] = {}

    for cf in custom_formats or []:
        c_name = str(cf.get("name") or "").strip()
        if not c_name:
            continue
        key = c_name.lower()
        cf_name_canonical[key] = c_name
        score_by_name[key] = int(cf.get("score", 0))
        if cf.get("trash_id"):
            score_by_trash_id[str(cf["trash_id"]).lower()] = int(cf.get("score", 0))
        if cf.get("id") is not None:
            cf_id_by_name[key] = int(cf["id"])

    # Also check raw_profile["formatItems"] for explicit score overrides or trash_id mappings.
    raw_fi = raw_profile.get("formatItems") or {}
    if isinstance(raw_fi, dict):
        for fi_name, fi_val in raw_fi.items():
            key = str(fi_name).strip().lower()
            if isinstance(fi_val, int) and not isinstance(fi_val, bool):
                score_by_name[key] = fi_val
            elif isinstance(fi_val, str) and fi_val.lower() in score_by_trash_id and key not in score_by_name:
                score_by_name[key] = score_by_trash_id[fi_val.lower()]

    for arr_cf in all_arr_cfs or []:
        if isinstance(arr_cf, dict) and arr_cf.get("name") and arr_cf.get("id") is not None:
            key = str(arr_cf["name"]).strip().lower()
            cf_id_by_name[key] = int(arr_cf["id"])
            cf_name_canonical.setdefault(key, str(arr_cf["name"]).strip())

    # Preserve existing non-TRaSH custom format scores if updating an existing profile.
    existing_match = next(
        (p for p in (existing_profiles or []) if str(p.get("name", "")).strip().lower() == name.lower()),
        None,
    )
    existing_scores_by_id: dict[int, int] = {}
    if existing_match:
        for fi in existing_match.get("formatItems") or []:
            if isinstance(fi, dict) and fi.get("format") is not None:
                existing_scores_by_id[int(fi["format"])] = int(fi.get("score", 0))

    format_items: list[dict[str, Any]] = []
    seen_cf_ids: set[int] = set()
    for key, cf_id in cf_id_by_name.items():
        if cf_id in seen_cf_ids:
            continue
        seen_cf_ids.add(cf_id)
        if key in score_by_name:
            score = score_by_name[key]
        else:
            score = existing_scores_by_id.get(cf_id, 0)
        format_items.append({
            "format": cf_id,
            "name": cf_name_canonical.get(key, key),
            "score": int(score),
        })

    profile_payload: dict[str, Any] = {
        "name": name,
        "upgradeAllowed": bool(raw_profile.get("upgradeAllowed", True)),
        "cutoff": int(cutoff_id),
        "minFormatScore": int(raw_profile.get("minFormatScore", 0)),
        "cutoffFormatScore": int(raw_profile.get("cutoffFormatScore", 10000)),
        "minUpgradeFormatScore": int(raw_profile.get("minUpgradeFormatScore", 1)),
        "items": arr_items,
        "formatItems": format_items,
    }
    if kind == ServiceKind.radarr or "language" in raw_profile or (schema and "language" in schema):
        lang_raw = raw_profile.get("language")
        if isinstance(lang_raw, dict) and "id" in lang_raw:
            profile_payload["language"] = lang_raw
        elif isinstance(schema, dict) and isinstance(schema.get("language"), dict):
            profile_payload["language"] = schema["language"]
        elif existing_match and isinstance(existing_match.get("language"), dict):
            profile_payload["language"] = existing_match["language"]
        elif kind == ServiceKind.radarr:
            lang_name = str(lang_raw or "Original")
            lang_id = -2 if lang_name.lower() == "original" else 1
            profile_payload["language"] = {"id": lang_id, "name": lang_name}

    return profile_payload


# ---------------------------------------------------------------- idempotent apply logic


async def apply_trash_bundle(arr: ArrAdapter, bundle: TrashBundle) -> dict[str, Any]:
    """Idempotently sync a parsed `TrashBundle` into a Radarr or Sonarr adapter instance."""
    qd_report = await arr.ensure_quality_definitions(bundle.quality_definitions)

    existing_cfs = await arr.custom_formats()
    cf_created: list[str] = []
    cf_updated: list[str] = []
    cf_unchanged: list[str] = []
    synced_cfs: list[dict[str, Any]] = []

    for cf in bundle.custom_formats:
        saved_cf, action = await arr.ensure_custom_format(cf, existing=existing_cfs)
        cf_with_id = {**cf, "id": saved_cf.get("id")}
        synced_cfs.append(cf_with_id)
        if action == "created":
            cf_created.append(cf["name"])
            existing_cfs.append(saved_cf)
        elif action == "updated":
            cf_updated.append(cf["name"])
            existing_cfs = [saved_cf if f.get("id") == saved_cf.get("id") else f for f in existing_cfs]
        else:
            cf_unchanged.append(cf["name"])

    existing_profiles = await arr.quality_profiles()
    schema = await arr.quality_profile_schema()
    target_name = str(bundle.raw_profile.get("name") or "").strip()
    user_profiles_kept = [
        str(p.get("name"))
        for p in existing_profiles
        if p.get("name") and str(p.get("name")).strip().lower() != target_name.lower()
    ]

    profile_payload = parse_quality_profile(
        bundle.raw_profile,
        synced_cfs,
        existing_profiles=existing_profiles,
        schema=schema,
        all_arr_cfs=existing_cfs,
        kind=bundle.kind,
    )
    saved_profile, profile_action = await arr.ensure_quality_profile(profile_payload, existing=existing_profiles)

    return {
        "kind": bundle.kind.value,
        "profile_name": saved_profile.get("name", target_name),
        "profile_id": saved_profile.get("id"),
        "profile_action": profile_action,
        "custom_formats_created": cf_created,
        "custom_formats_updated": cf_updated,
        "custom_formats_unchanged": cf_unchanged,
        "quality_definitions_updated": qd_report["updated"],
        "quality_definitions_unchanged": qd_report["unchanged"],
        "user_profiles_kept": user_profiles_kept,
    }


def format_sync_summary(app_name: str, report: dict[str, Any]) -> str:
    """Build a clear plain-English summary of every change applied to `app_name`."""
    p_name = report["profile_name"]
    p_action = report["profile_action"]
    cf_c = len(report["custom_formats_created"])
    cf_u = len(report["custom_formats_updated"])
    cf_same = len(report["custom_formats_unchanged"])
    qd_u = len(report["quality_definitions_updated"])
    kept = report["user_profiles_kept"]

    parts = [f"Profile '{p_name}' {p_action}"]
    cf_bits = []
    if cf_c:
        cf_bits.append(f"{cf_c} created")
    if cf_u:
        cf_bits.append(f"{cf_u} updated")
    if cf_same:
        cf_bits.append(f"{cf_same} unchanged")
    if cf_bits:
        parts.append(f"custom formats: {', '.join(cf_bits)}")
    if qd_u:
        parts.append(f"{qd_u} quality sizes updated")
    else:
        parts.append("quality sizes up to date")
    if kept:
        parts.append(f"kept {len(kept)} existing profile(s): {', '.join(kept)}")
    return f"{app_name}: " + "; ".join(parts) + "."


async def sync_app_trash(
    db: AsyncSession,
    job: Job,
    kind: ServiceKind,
    profile_choice: str = DEFAULT_TRASH_PROFILE,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any] | None:
    """Download and apply TRaSH quality definitions, custom formats, and profile for one *arr app."""
    name = kind.value.capitalize()
    expected_profile = target_profile_name(kind, profile_choice)
    step = job.step(f"Apply TRaSH quality profile ({expected_profile}) to {name}")
    svc = await get_service(db, kind)
    if svc is None or not svc.enabled:
        job.skip(step, f"{name} is not connected.")
        return None
    try:
        job.say(f"Downloading TRaSH-Guides '{expected_profile}' definitions for {name}...")
        bundle = await fetch_trash_bundle(kind, profile_choice, client=client)
        async with adapter_for(db, kind) as arr:
            report = await apply_trash_bundle(arr, bundle)
        summary = format_sync_summary(name, report)
        job.say(summary)
        if report["custom_formats_created"]:
            job.say(f"  Created custom formats in {name}: {', '.join(report['custom_formats_created'])}")
        if report["custom_formats_updated"]:
            job.say(f"  Updated custom formats in {name}: {', '.join(report['custom_formats_updated'])}")
        job.ok(step, summary)
        return report
    except Exception as exc:  # noqa: BLE001
        job.fail(step, exc)
        return None


async def run_trash_sync(
    job: Job,
    profile_choice: str | None = None,
    kinds: list[ServiceKind] | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Background job body: sync TRaSH quality profiles into Radarr and/or Sonarr and persist setting."""
    target_kinds = kinds or [ServiceKind.radarr, ServiceKind.sonarr]
    async with sessionmaker()() as db:
        chosen = normalize_preset_key(profile_choice or await get_setting(db, "trash_profile") or DEFAULT_TRASH_PROFILE)
        await set_settings(db, {"trash_profile": chosen})

        reports: dict[str, Any] = {}
        for kind in target_kinds:
            rep = await sync_app_trash(db, job, kind, chosen, client=client)
            if rep is not None:
                reports[kind.value] = rep

        failed = [s.name for s in job.steps if s.status == "failed"]
        sync_record = {
            "profile": chosen,
            "synced_at": datetime.now(UTC).isoformat(),
            "status": "failed" if failed else "ok",
            "apps": reports,
        }
        await set_settings(db, {"trash_last_sync": sync_record})
        msg = (
            f"TRaSH quality profiles sync finished with errors: {', '.join(failed)}"
            if failed
            else f"Synced TRaSH quality profiles ({chosen}) to {', '.join(reports) or 'no connected apps'}."
        )
        await log_event(db, "trash", msg, level="error" if failed else "info", details=sync_record)
        return {"profile": chosen, "apps": reports, "failed": failed}


async def get_trash_status(db: AsyncSession) -> dict[str, Any]:
    """Return current TRaSH profile setting, available presets, last sync info, and live per-app status."""
    chosen = await get_setting(db, "trash_profile")
    last_sync = await get_setting(db, "trash_last_sync")
    effective_choice = chosen or DEFAULT_TRASH_PROFILE

    apps_status: dict[str, Any] = {}
    for kind in (ServiceKind.radarr, ServiceKind.sonarr):
        svc = await get_service(db, kind)
        expected_name = target_profile_name(kind, effective_choice)
        if svc is None or not svc.enabled:
            apps_status[kind.value] = {
                "connected": False,
                "reachable": False,
                "target_profile": expected_name,
                "synced": False,
                "profiles": [],
                "custom_format_count": 0,
            }
            continue
        try:
            async with adapter_for(db, kind) as arr:
                profiles, cfs = await asyncio.gather(arr.quality_profiles(), arr.custom_formats())
            profile_names = [str(p.get("name")) for p in profiles if p.get("name")]
            synced = any(n.strip().lower() == expected_name.lower() for n in profile_names)
            apps_status[kind.value] = {
                "connected": True,
                "reachable": True,
                "target_profile": expected_name,
                "synced": synced,
                "profiles": profile_names,
                "custom_format_count": len(cfs),
            }
        except UnifierrError:
            apps_status[kind.value] = {
                "connected": True,
                "reachable": False,
                "target_profile": expected_name,
                "synced": False,
                "profiles": [],
                "custom_format_count": 0,
            }

    return {
        "chosen_profile": chosen,
        "available_profiles": [p.to_dict() for p in TRASH_PRESETS.values()],
        "last_sync": last_sync,
        "apps": apps_status,
    }
