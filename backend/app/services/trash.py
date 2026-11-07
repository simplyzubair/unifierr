"""Apply TRaSH-Guides quality profiles and custom formats to Radarr / Sonarr.

Opt-in via the ``trash_profiles`` setting (Settings -> Apps). The public TRaSH
JSON is fetched at apply time over HTTPS; nothing is bundled. Apply is
non-destructive: it only creates/updates TRaSH-named custom formats and quality
profiles, and never deletes or edits the user's own profiles.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.adapters.base import ServiceKind
from app.core.errors import ServiceUnavailable
from app.services.common import adapter_for, get_service, get_setting, log_event

log = logging.getLogger("unifierr.trash")

# Public TRaSH-Guides JSON roots (master branch). Custom formats live one file
# per format; quality profiles reference custom formats by name.
RADARR_CF = "https://raw.githubusercontent.com/TRaSH-Guides/Guides/master/docs/json/radarr/cf"
SONARR_CF = "https://raw.githubusercontent.com/TRaSH-Guides/Guides/master/docs/json/sonarr/cf"
RADARR_PROFILES = "https://raw.githubusercontent.com/TRaSH-Guides/Guides/master/docs/json/radarr/quality-profiles"
SONARR_PROFILES = "https://raw.githubusercontent.com/TRaSH-Guides/Guides/master/docs/json/sonarr/quality-profiles"

# A single sensible default profile per app. Users can change this in Settings.
DEFAULT_PROFILE = {
    ServiceKind.radarr: "remux-1080p-web-2160p",
    ServiceKind.sonarr: "web-2160p",
}

_TIMEOUT = 20.0


def _profile_cf_names(profile: dict[str, Any]) -> list[str]:
    """Custom-format names a TRaSH quality profile wants, in a stable order."""
    names: list[str] = []
    fmt = profile.get("formatItems")
    if isinstance(fmt, dict):
        names.extend(str(k) for k in fmt.keys())
    elif isinstance(fmt, list):
        names.extend(str(f.get("name", "")) for f in fmt if isinstance(f, dict) and f.get("name"))
    return [n for n in names if n]


async def _fetch_json(client: httpx.AsyncClient, url: str) -> Any:
    try:
        resp = await client.get(url, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise ServiceUnavailable(
            "Could not download TRaSH-Guides data",
            explanation=f"Unifierr could not reach the TRaSH-Guides repository ({url}).",
            fix="Check that this machine can reach the internet, then try again.",
        ) from exc
    if resp.status_code >= 400:
        raise ServiceUnavailable(
            "Could not download TRaSH-Guides data",
            explanation=f"The TRaSH-Guides file was not found ({resp.status_code}).",
            fix="The TRaSH-Guides repository may have moved these files; update Unifierr.",
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise ServiceUnavailable(
            "TRaSH-Guides data is not readable",
            explanation="The downloaded file was not valid JSON.",
            fix="Try again later; this is usually a temporary upstream issue.",
        ) from exc


async def apply_trash_profiles(db, job=None, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """Apply the default TRaSH profile + its custom formats to every connected *arr.

    Returns a report of what was created/updated/skipped. ``job`` is optional and
    lets callers (e.g. wiring) record plain-English steps.
    """
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=_TIMEOUT)
    report: dict[str, Any] = {"radarr": [], "sonarr": [], "errors": []}
    try:
        for kind in (ServiceKind.radarr, ServiceKind.sonarr):
            svc = await get_service(db, kind)
            if svc is None:
                continue
            cf_dir = RADARR_CF if kind is ServiceKind.radarr else SONARR_CF
            profiles_dir = RADARR_PROFILES if kind is ServiceKind.radarr else SONARR_PROFILES
            profile_name = await get_setting(db, "trash_profile") or DEFAULT_PROFILE[kind]
            label = svc.name

            # 1. Download the named quality profile.
            profile = await _fetch_json(client, f"{profiles_dir}/{profile_name}.json")
            if not isinstance(profile, dict):
                raise ServiceUnavailable("TRaSH profile was not a JSON object")

            # 2. Import every custom format the profile references.
            cf_names = _profile_cf_names(profile)
            cf_id_by_name: dict[str, int] = {}
            async with adapter_for(db, kind) as arr:
                for cf_name in cf_names:
                    slug = cf_name.lower().replace(" ", "-")
                    cf = await _fetch_json(client, f"{cf_dir}/{slug}.json")
                    if isinstance(cf, dict) and cf.get("name"):
                        stored = await arr.ensure_custom_format(cf)
                        cf_id_by_name[str(cf.get("name")).lower()] = int(stored["id"])
                    else:
                        report["errors"].append(f"{label}: custom format file for {cf_name} was empty")

                # 3. Build the *arr quality-profile body from the TRaSH profile.
                desired = _build_profile(profile, cf_id_by_name, await arr.quality_definitions())
                await arr.ensure_quality_profile(desired)
            report[kind.value].append({"profile": profile_name, "custom_formats": len(cf_id_by_name)})
            await log_event(db, "trash", f"Applied TRaSH profile '{profile_name}' to {label}.")
            if job is not None:
                job.ok(job.step(f"TRaSH profile for {label}"),
                       f"Applied '{profile_name}' with {len(cf_id_by_name)} custom formats.")
    except ServiceUnavailable as exc:
        if job is not None:
            job.fail(job.step("Apply TRaSH profiles"), exc)
        report["errors"].append(str(exc))
    finally:
        if own_client:
            await client.aclose()
    return report


def _build_profile(profile: dict[str, Any], cf_id_by_name: dict[str, int],
                   definitions: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert a TRaSH quality profile into an *arr ``/qualityprofile`` body."""
    body: dict[str, Any] = {
        "name": str(profile.get("name", "")).strip() or "TRaSH",
        "upgradeAllowed": bool(profile.get("upgradeAllowed", False)),
        "cutoff": int(profile.get("cutoff") or 0),
        "minFormatScore": int(profile.get("minFormatScore") or 0),
        "cutoffFormatScore": int(profile.get("cutoffFormatScore") or 0),
        "minUpgradeFormatScore": int(profile.get("minUpgradeFormatScore") or 0),
    }
    # Quality items: TRaSH lists quality names; resolve to the app's quality ids.
    items: list[dict[str, Any]] = []
    for it in profile.get("items") or []:
        qname = str((it.get("quality") or {}).get("name") or it.get("name") or "")
        sub: list[dict[str, Any]] = []
        for s in it.get("items") or []:
            sqname = str((s.get("quality") or {}).get("name") or s.get("name") or "")
            sub.append({"quality": _find_quality_id(definitions, sqname), "allowed": bool(s.get("allowed", True))})
        items.append({"quality": _find_quality_id(definitions, qname),
                      "allowed": bool(it.get("allowed", True)), "items": sub})
    body["items"] = items
    # Custom-format scores: TRaSH names -> imported *arr format ids.
    fmt = profile.get("formatItems")
    scores: list[dict[str, int]] = []
    if isinstance(fmt, dict):
        for name, score in fmt.items():
            cfid = cf_id_by_name.get(str(name).lower())
            if cfid is not None:
                scores.append({"format": cfid, "score": int(score or 0)})
    body["formatItems"] = scores
    return body


def _find_quality_id(definitions: list[dict[str, Any]], name: str) -> int:
    """Resolve a quality name to its id from the app's quality definitions."""
    name = str(name).strip().lower()
    for d in definitions:
        q = d.get("quality") or {}
        qname = str(q.get("name") or "").strip().lower()
        if qname == name:
            return int(q.get("id") or d.get("id") or 0)
    return 0


async def is_trash_enabled(db) -> bool:
    return bool(await get_setting(db, "trash_profiles"))
