"""Adapter methods for TRaSH custom formats / quality profiles (idempotency)."""
from app.adapters.base import Connection, ServiceKind
from app.adapters.radarr import RadarrAdapter

RR = "http://radarr:7878"


def radarr():
    return RadarrAdapter(Connection(ServiceKind.radarr, RR, api_key="key"))


async def test_ensure_custom_format_creates(mock):
    mock.get(f"{RR}/api/v3/customformat").respond(200, json=[])
    post = mock.post(f"{RR}/api/v3/customformat").respond(200, json={"id": 5, "name": "x264"})
    async with radarr() as a:
        stored = await a.ensure_custom_format({"name": "x264", "specifications": []})
    assert stored["id"] == 5
    assert post.calls.last.request.url.path.endswith("/customformat")


async def test_ensure_custom_format_skips_when_identical(mock):
    existing = {"id": 5, "name": "x264", "includeCustomFormatWhenRenaming": False, "specifications": []}
    mock.get(f"{RR}/api/v3/customformat").respond(200, json=[existing])
    async with radarr() as a:
        stored = await a.ensure_custom_format({"name": "x264", "specifications": []})
    assert stored["id"] == 5
    assert len(mock.calls) == 1  # only the GET happened


async def test_ensure_quality_profile_creates(mock):
    mock.get(f"{RR}/api/v3/qualityprofile").respond(200, json=[])
    post = mock.post(f"{RR}/api/v3/qualityprofile").respond(200, json={"id": 3, "name": "TRaSH"})
    async with radarr() as a:
        stored = await a.ensure_quality_profile({"name": "TRaSH", "upgradeAllowed": True, "cutoff": 100})
    assert stored["id"] == 3
    assert post.calls.last.request.url.path.endswith("/qualityprofile")


async def test_ensure_quality_profile_skips_when_identical(mock):
    existing = {"id": 3, "name": "TRaSH", "upgradeAllowed": True, "cutoff": 100, "items": []}
    mock.get(f"{RR}/api/v3/qualityprofile").respond(200, json=[existing])
    async with radarr() as a:
        stored = await a.ensure_quality_profile(
            {"name": "TRaSH", "upgradeAllowed": True, "cutoff": 100, "items": []})
    assert stored["id"] == 3
    assert len(mock.calls) == 1  # only the GET
