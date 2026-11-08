"""Tests for TRaSH-Guides parsing, mapping, idempotent sync, and API routes (no live network)."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from app.adapters.base import Connection, ServiceKind
from app.adapters.radarr import RadarrAdapter
from app.core.db import sessionmaker
from app.core.errors import ServiceUnavailable
from app.services.common import set_settings
from app.services.installer import save_service
from app.services.jobs import Job, jobs
from app.services.trash import (
    TRASH_BASE_URL,
    apply_trash_bundle,
    fetch_trash_bundle,
    fetch_trash_json,
    parse_custom_format,
    parse_quality_definitions,
    parse_quality_profile,
)
from app.services.wiring import run_wiring
from tests.conftest import CSRF, make_admin

RADARR_URL = "http://radarr:7878"
SONARR_URL = "http://sonarr:8989"

# ---------------------------------------------------------------- canned TRaSH JSON fixtures

RADARR_QUALITY_SIZE = {
    "trash_id": "aed34b9f60ee115dfa7918b742336277",
    "type": "movie",
    "qualities": [
        {"quality": "WEBDL-1080p", "min": 12.5, "preferred": 1999, "max": 2000},
        {"quality": "Bluray-1080p", "min": 50.8, "preferred": 1999, "max": 2000},
    ],
}

SONARR_QUALITY_SIZE = {
    "trash_id": "bef99584217af744e404ed44a33af589",
    "type": "series",
    "qualities": [
        {"quality": "WEBDL-1080p", "min": 15.0, "preferred": 995, "max": 1000},
        {"quality": "WEBRip-1080p", "min": 15.0, "preferred": 995, "max": 1000},
    ],
}

CF_BLURAY_TIER_01 = {
    "trash_id": "ed27ebfef2f323e964fb1f61391bcb35",
    "trash_scores": {"default": 1800, "sqp-1-1080p": 1100},
    "name": "HD Bluray Tier 01",
    "includeCustomFormatWhenRenaming": False,
    "specifications": [
        {
            "name": "BLURAY",
            "implementation": "SourceSpecification",
            "negate": False,
            "required": True,
            "fields": {"value": 9},
        },
        {
            "name": "CtrlHD",
            "implementation": "ReleaseGroupSpecification",
            "negate": False,
            "required": False,
            "fields": {"value": "^(CtrlHD)$"},
        },
    ],
}

CF_WEB_TIER_01 = {
    "trash_id": "c20f169ef63c5f40c2def54abaf4438e",
    "trash_scores": {"default": 1700},
    "name": "WEB Tier 01",
    "includeCustomFormatWhenRenaming": False,
    "specifications": [
        {
            "name": "NTb",
            "implementation": "ReleaseGroupSpecification",
            "negate": False,
            "required": False,
            "fields": {"value": "^(NTb)$"},
        }
    ],
}

CF_BR_DISK = {
    "trash_id": "ed38b889b31be83fda192888e2286d83",
    "trash_scores": {"default": -10000},
    "name": "BR-DISK",
    "includeCustomFormatWhenRenaming": False,
    "specifications": [
        {
            "name": "BR-DISK",
            "implementation": "ReleaseTitleSpecification",
            "negate": False,
            "required": True,
            "fields": {"value": "BR-DISK"},
        }
    ],
}

RADARR_PROFILE_HD_BLURAY_WEB = {
    "trash_id": "d1d67249d3890e49bc12e275d989a7e9",
    "name": "HD Bluray + WEB",
    "upgradeAllowed": True,
    "cutoff": "Bluray-1080p",
    "minFormatScore": 0,
    "cutoffFormatScore": 10000,
    "minUpgradeFormatScore": 1,
    "language": "Original",
    "items": [
        {"name": "Bluray-1080p", "allowed": True},
        {"name": "WEB 1080p", "allowed": True, "items": ["WEBRip-1080p", "WEBDL-1080p"]},
        {"name": "Unknown", "allowed": False},
    ],
    "formatItems": {
        "HD Bluray Tier 01": "ed27ebfef2f323e964fb1f61391bcb35",
        "WEB Tier 01": "c20f169ef63c5f40c2def54abaf4438e",
    },
}

SONARR_PROFILE_WEB_1080P = {
    "trash_id": "72dae194fc92bf828f32cde7744e51a1",
    "name": "WEB-1080p",
    "upgradeAllowed": True,
    "cutoff": "WEB 1080p",
    "minFormatScore": 0,
    "cutoffFormatScore": 10000,
    "minUpgradeFormatScore": 1,
    "items": [
        {"name": "WEB 1080p", "allowed": True, "items": ["WEBRip-1080p", "WEBDL-1080p"]},
        {"name": "SDTV", "allowed": False},
    ],
    "formatItems": {
        "WEB Tier 01": "c20f169ef63c5f40c2def54abaf4438e",
    },
}

UNWANTED_GROUP = {
    "name": "[Unwanted] Unwanted Formats",
    "trash_id": "a3ac6af01d78e4f21fcb75f601ac96df",
    "custom_formats": [
        {"name": "BR-DISK", "trash_id": "ed38b889b31be83fda192888e2286d83", "required": False, "default": True},
        {"name": "Obfuscated", "trash_id": "7357cf5161efbf8c4d5d0c30b4815ee2", "required": False},
    ],
    "quality_profiles": {
        "include": {
            "HD Bluray + WEB": "d1d67249d3890e49bc12e275d989a7e9",
            "WEB-1080p": "72dae194fc92bf828f32cde7744e51a1",
        }
    },
}


# ---------------------------------------------------------------- unit tests: parsing + mapping


def test_parse_quality_definitions():
    defs = parse_quality_definitions(RADARR_QUALITY_SIZE)
    assert defs == [
        {"quality": "WEBDL-1080p", "min": 12.5, "preferred": 1999.0, "max": 2000.0},
        {"quality": "Bluray-1080p", "min": 50.8, "preferred": 1999.0, "max": 2000.0},
    ]


def test_parse_custom_format_scores_and_specs():
    cf = parse_custom_format(CF_BLURAY_TIER_01)
    assert cf["name"] == "HD Bluray Tier 01"
    assert cf["score"] == 1800
    assert cf["specifications"][0]["fields"] == [{"name": "value", "value": 9}]

    # Score set override (e.g. sqp-1-1080p)
    cf_sqp = parse_custom_format(CF_BLURAY_TIER_01, score_set="sqp-1-1080p")
    assert cf_sqp["score"] == 1100

    # Explicit override
    cf_over = parse_custom_format(CF_BLURAY_TIER_01, score_override=-500)
    assert cf_over["score"] == -500


def test_parse_quality_profile_maps_groups_cutoff_and_format_scores():
    cfs = [
        {**parse_custom_format(CF_BLURAY_TIER_01), "id": 101},
        {**parse_custom_format(CF_WEB_TIER_01), "id": 102},
        {**parse_custom_format(CF_BR_DISK), "id": 103},
    ]
    all_arr_cfs = [
        {"id": 101, "name": "HD Bluray Tier 01"},
        {"id": 102, "name": "WEB Tier 01"},
        {"id": 103, "name": "BR-DISK"},
        {"id": 999, "name": "User Custom Format"},
    ]
    existing_profiles = [
        {
            "id": 1,
            "name": "Any",
            "items": [
                {
                    "quality": {"id": 0, "name": "Unknown", "source": "unknown", "resolution": 0},
                    "items": [],
                    "allowed": True,
                },
                {
                    "quality": {"id": 4, "name": "HDTV-720p", "source": "tv", "resolution": 720},
                    "items": [],
                    "allowed": True,
                },
            ],
        }
    ]
    profile = parse_quality_profile(
        RADARR_PROFILE_HD_BLURAY_WEB,
        cfs,
        existing_profiles=existing_profiles,
        all_arr_cfs=all_arr_cfs,
        kind=ServiceKind.radarr,
    )
    assert profile["name"] == "HD Bluray + WEB"
    assert profile["cutoff"] == 7  # Bluray-1080p quality id
    assert profile["language"] == {"id": -2, "name": "Original"}
    # Highest item (Bluray-1080p) is at the end of Radarr's bottom-up items array
    assert profile["items"][-1]["quality"]["name"] == "Bluray-1080p"
    assert profile["items"][-1]["allowed"] is True
    # Group WEB 1080p has group id 1000 and contains WEBRip-1080p + WEBDL-1080p
    web_group = next(it for it in profile["items"] if it.get("name") == "WEB 1080p")
    assert web_group["id"] == 1000 and web_group["allowed"] is True
    assert [s["quality"]["name"] for s in web_group["items"]] == ["WEBRip-1080p", "WEBDL-1080p"]
    # Server quality HDTV-720p not in TRaSH list is preserved as allowed=False
    hdtv = next(it for it in profile["items"] if (it.get("quality") or {}).get("name") == "HDTV-720p")
    assert hdtv["allowed"] is False

    # Format scores mapped properly; unrelated user CF gets score 0
    scores = {f["name"]: (f["format"], f["score"]) for f in profile["formatItems"]}
    assert scores["HD Bluray Tier 01"] == (101, 1800)
    assert scores["WEB Tier 01"] == (102, 1700)
    assert scores["BR-DISK"] == (103, -10000)
    assert scores["User Custom Format"] == (999, 0)


def test_parse_quality_profile_group_cutoff_sonarr():
    cfs = [{**parse_custom_format(CF_WEB_TIER_01), "id": 11}]
    profile = parse_quality_profile(SONARR_PROFILE_WEB_1080P, cfs, kind=ServiceKind.sonarr)
    assert profile["name"] == "WEB-1080p"
    # Cutoff is the group "WEB 1080p" -> group id 1000
    assert profile["cutoff"] == 1000
    assert "language" not in profile


# ---------------------------------------------------------------- fetch + idempotent apply tests


def _mock_trash_github(router: respx.MockRouter):
    router.get(f"{TRASH_BASE_URL}/radarr/quality-size/movie.json").respond(json=RADARR_QUALITY_SIZE)
    router.get(f"{TRASH_BASE_URL}/radarr/quality-profiles/hd-bluray-web.json").respond(
        json=RADARR_PROFILE_HD_BLURAY_WEB
    )
    router.get(f"{TRASH_BASE_URL}/radarr/cf-groups/unwanted-formats.json").respond(json=UNWANTED_GROUP)
    router.get(f"{TRASH_BASE_URL}/radarr/cf/hd-bluray-tier-01.json").respond(json=CF_BLURAY_TIER_01)
    router.get(f"{TRASH_BASE_URL}/radarr/cf/web-tier-01.json").respond(json=CF_WEB_TIER_01)
    router.get(f"{TRASH_BASE_URL}/radarr/cf/br-disk.json").respond(json=CF_BR_DISK)

    router.get(f"{TRASH_BASE_URL}/sonarr/quality-size/series.json").respond(json=SONARR_QUALITY_SIZE)
    router.get(f"{TRASH_BASE_URL}/sonarr/quality-profiles/web-1080p.json").respond(json=SONARR_PROFILE_WEB_1080P)
    router.get(f"{TRASH_BASE_URL}/sonarr/cf-groups/unwanted-formats.json").respond(json=UNWANTED_GROUP)
    router.get(f"{TRASH_BASE_URL}/sonarr/cf/web-tier-01.json").respond(json=CF_WEB_TIER_01)
    router.get(f"{TRASH_BASE_URL}/sonarr/cf/br-disk.json").respond(json=CF_BR_DISK)


async def test_fetch_trash_json_timeout_maps_to_service_unavailable():
    with respx.mock(assert_all_called=False) as m:
        m.get(f"{TRASH_BASE_URL}/radarr/quality-size/movie.json").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )
        with pytest.raises(ServiceUnavailable) as exc_info:
            await fetch_trash_json("radarr/quality-size/movie.json")
        assert "did not answer in time" in exc_info.value.message
        assert exc_info.value.fix


async def test_apply_trash_bundle_idempotent_and_keeps_user_profiles():
    with respx.mock(assert_all_called=False) as m:
        _mock_trash_github(m)

        # Stateful in-memory Radarr store to verify 1st run (creates) vs 2nd run (no-op unchanged)
        qdefs = [
            {
                "id": 1, "quality": {"id": 3, "name": "WEBDL-1080p"},
                "minSize": 5.0, "maxSize": 100.0, "preferredSize": 95.0,
            },
            {
                "id": 2, "quality": {"id": 7, "name": "Bluray-1080p"},
                "minSize": 10.0, "maxSize": 100.0, "preferredSize": 95.0,
            },
        ]
        cfs: list[dict] = []
        profiles: list[dict] = [
            {"id": 1, "name": "Any", "upgradeAllowed": True, "cutoff": 0, "items": [], "formatItems": []},
            {"id": 2, "name": "User Favorite 4K", "upgradeAllowed": True, "cutoff": 19, "items": [], "formatItems": []},
        ]
        put_qdef_calls: list[int] = []
        post_cf_calls: list[str] = []
        put_cf_calls: list[int] = []
        post_prof_calls: list[str] = []
        put_prof_calls: list[int] = []

        m.get(f"{RADARR_URL}/api/v3/qualitydefinition").mock(side_effect=lambda _: httpx.Response(200, json=qdefs))

        def update_qdef(request: httpx.Request, def_id: str) -> httpx.Response:
            payload = json.loads(request.content)
            put_qdef_calls.append(int(def_id))
            for idx, d in enumerate(qdefs):
                if d["id"] == int(def_id):
                    qdefs[idx] = payload
            return httpx.Response(200, json=payload)

        m.put(url__regex=rf"^{RADARR_URL}/api/v3/qualitydefinition/(\d+)$").mock(
            side_effect=lambda req: update_qdef(req, req.url.path.rsplit("/", 1)[1])
        )
        m.get(f"{RADARR_URL}/api/v3/customformat").mock(side_effect=lambda _: httpx.Response(200, json=cfs))

        def create_cf(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            created = {**payload, "id": len(cfs) + 10}
            cfs.append(created)
            post_cf_calls.append(created["name"])
            return httpx.Response(201, json=created)

        m.post(f"{RADARR_URL}/api/v3/customformat").mock(side_effect=create_cf)
        m.put(url__regex=rf"^{RADARR_URL}/api/v3/customformat/\d+$").mock(
            side_effect=lambda req: (put_cf_calls.append(1), httpx.Response(200, json=json.loads(req.content)))[1]
        )
        m.get(f"{RADARR_URL}/api/v3/qualityprofile").mock(side_effect=lambda _: httpx.Response(200, json=profiles))
        m.get(f"{RADARR_URL}/api/v3/qualityprofile/schema").respond(404)

        def create_prof(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            created = {**payload, "id": len(profiles) + 1}
            profiles.append(created)
            post_prof_calls.append(created["name"])
            return httpx.Response(201, json=created)

        m.post(f"{RADARR_URL}/api/v3/qualityprofile").mock(side_effect=create_prof)
        m.put(url__regex=rf"^{RADARR_URL}/api/v3/qualityprofile/\d+$").mock(
            side_effect=lambda req: (put_prof_calls.append(1), httpx.Response(200, json=json.loads(req.content)))[1]
        )

        bundle = await fetch_trash_bundle(ServiceKind.radarr, "hd-1080p")
        async with RadarrAdapter(Connection(ServiceKind.radarr, RADARR_URL, api_key="k")) as arr:
            # First run: creates 3 custom formats, updates 2 quality definitions, creates 'HD Bluray + WEB'
            rep1 = await apply_trash_bundle(arr, bundle)
            assert rep1["profile_action"] == "created"
            assert rep1["profile_name"] == "HD Bluray + WEB"
            assert set(rep1["custom_formats_created"]) == {"HD Bluray Tier 01", "WEB Tier 01", "BR-DISK"}
            assert rep1["custom_formats_unchanged"] == []
            assert set(rep1["quality_definitions_updated"]) == {"WEBDL-1080p", "Bluray-1080p"}
            assert rep1["user_profiles_kept"] == ["Any", "User Favorite 4K"]
            assert len(profiles) == 3  # 2 user profiles + 1 TRaSH profile

            # Second run: 100% idempotent — nothing created or updated
            rep2 = await apply_trash_bundle(arr, bundle)
            assert rep2["profile_action"] == "unchanged"
            assert rep2["custom_formats_created"] == []
            assert rep2["custom_formats_updated"] == []
            assert set(rep2["custom_formats_unchanged"]) == {"HD Bluray Tier 01", "WEB Tier 01", "BR-DISK"}
            assert rep2["quality_definitions_updated"] == []
            assert set(rep2["quality_definitions_unchanged"]) == {"WEBDL-1080p", "Bluray-1080p"}
            assert not put_cf_calls and not put_prof_calls


async def test_trash_api_status_and_apply_job_persists_setting(client):
    await make_admin(client)
    async with sessionmaker()() as db:
        await save_service(db, ServiceKind.radarr, base_url=RADARR_URL, api_key="k" * 32)
        await save_service(db, ServiceKind.sonarr, base_url=SONARR_URL, api_key="k" * 32)

    with respx.mock(assert_all_called=False) as m:
        _mock_trash_github(m)
        for base in (RADARR_URL, SONARR_URL):
            m.get(f"{base}/api/v3/qualitydefinition").respond(json=[])
            m.get(f"{base}/api/v3/customformat").respond(json=[])
            m.post(f"{base}/api/v3/customformat").mock(
                side_effect=lambda req: httpx.Response(201, json={**json.loads(req.content), "id": 1})
            )
            m.get(f"{base}/api/v3/qualityprofile").respond(json=[{"id": 1, "name": "Any"}])
            m.get(f"{base}/api/v3/qualityprofile/schema").respond(404)
            m.post(f"{base}/api/v3/qualityprofile").mock(
                side_effect=lambda req: httpx.Response(201, json={**json.loads(req.content), "id": 2})
            )

        status_before = (await client.get("/api/trash/status")).json()
        assert status_before["chosen_profile"] is None
        assert len(status_before["available_profiles"]) >= 4
        assert status_before["apps"]["radarr"]["connected"] is True
        assert status_before["apps"]["radarr"]["synced"] is False

        apply_resp = await client.post("/api/trash/apply", json={"profile": "hd-1080p"}, headers=CSRF)
        assert apply_resp.status_code == 200, apply_resp.text
        job_id = apply_resp.json()["job_id"]
        assert apply_resp.json()["profile"] == "hd-1080p"

        # Wait for the background job to complete
        for _ in range(40):
            job = jobs.get(job_id)
            if job and job.status in ("done", "failed"):
                break
            await asyncio.sleep(0.05)

        job_out = (await client.get(f"/api/jobs/{job_id}")).json()
        assert job_out["status"] == "done", job_out
        assert len(job_out["steps"]) == 2
        assert all(s["status"] == "ok" for s in job_out["steps"])

        # Setting is persisted in DB and exposed via /api/settings and /api/trash/status
        settings_out = (await client.get("/api/settings")).json()
        assert settings_out["trash_profile"] == "hd-1080p"
        assert settings_out["trash_last_sync"]["status"] == "ok"
        assert "radarr" in settings_out["trash_last_sync"]["apps"]
        assert "sonarr" in settings_out["trash_last_sync"]["apps"]


async def test_wiring_syncs_trash_when_profile_setting_is_configured(client):
    async with sessionmaker()() as db:
        await save_service(db, ServiceKind.radarr, base_url=RADARR_URL, api_key="k" * 32)
        await set_settings(db, {"trash_profile": "hd-1080p"})

    with respx.mock(assert_all_called=False) as m:
        _mock_trash_github(m)
        m.get(f"{RADARR_URL}/api/v3/rootfolder").respond(json=[{"id": 1, "path": "/data/media/movies"}])
        m.get(f"{RADARR_URL}/api/v3/qualitydefinition").respond(json=[])
        m.get(f"{RADARR_URL}/api/v3/customformat").respond(json=[])
        m.post(f"{RADARR_URL}/api/v3/customformat").mock(
            side_effect=lambda req: httpx.Response(201, json={**json.loads(req.content), "id": 1})
        )
        m.get(f"{RADARR_URL}/api/v3/qualityprofile").respond(json=[{"id": 1, "name": "Any"}])
        m.get(f"{RADARR_URL}/api/v3/qualityprofile/schema").respond(404)
        m.post(f"{RADARR_URL}/api/v3/qualityprofile").mock(
            side_effect=lambda req: httpx.Response(201, json={**json.loads(req.content), "id": 2})
        )

        job = Job(id="w", kind="wire")
        res = await run_wiring(job)
        assert res["failed"] == []
        radarr_trash_step = next(s for s in job.steps if "TRaSH" in s.name and "Radarr" in s.name)
        assert radarr_trash_step.status == "ok"
        assert "HD Bluray + WEB" in (radarr_trash_step.message or "")
