"""Tests for the TRaSH quality-profile mapping (pure functions)."""
from app.adapters._arr_common import _profile_matches, normalize_cf_payload
from app.services.trash import _build_profile, _find_quality_id, _profile_cf_names


def test_find_quality_id_resolves_names():
    definitions = [
        {"id": 1, "quality": {"id": 11, "name": "Remux-1080p"}},
        {"id": 2, "quality": {"id": 22, "name": "Bluray-1080p"}},
    ]
    assert _find_quality_id(definitions, "Remux-1080p") == 11
    assert _find_quality_id(definitions, "Bluray-1080p") == 22
    assert _find_quality_id(definitions, "missing") == 0


def test_build_profile_maps_names_to_ids():
    profile = {
        "name": "Remux-1080p - WEB-2160p",
        "upgradeAllowed": True,
        "cutoff": 100,
        "minFormatScore": 0,
        "cutoffFormatScore": 100,
        "items": [{"name": "Remux-1080p", "allowed": True, "items": [{"name": "Bluray-1080p"}]}],
        "formatItems": {"x264": "0", "Remux Tier 01": "1250"},
    }
    definitions = [
        {"id": 1, "quality": {"id": 11, "name": "Remux-1080p"}},
        {"id": 2, "quality": {"id": 22, "name": "Bluray-1080p"}},
    ]
    cf_ids = {"x264": 5, "remux tier 01": 9}
    body = _build_profile(profile, cf_ids, definitions)
    assert body["name"] == "Remux-1080p - WEB-2160p"
    assert body["cutoff"] == 100 and body["cutoffFormatScore"] == 100
    assert body["items"] == [{"quality": 11, "allowed": True, "items": [{"quality": 22, "allowed": True}]}]
    assert body["formatItems"] == [{"format": 5, "score": 0}, {"format": 9, "score": 1250}]


def test_profile_cf_names_order():
    profile = {"formatItems": {"b": "1", "a": "2"}}
    assert _profile_cf_names(profile) == ["b", "a"]


def test_normalize_cf_payload_handles_dict_fields():
    cf = {"name": "x264", "specifications": [
        {"name": "Source", "implementation": "SourceSpecification", "fields": {"value": "bluray"}}]}
    body = normalize_cf_payload(cf)
    assert body["name"] == "x264"
    assert body["specifications"][0]["fields"] == [{"name": "value", "value": "bluray"}]


def test_profile_matches_ignores_id_vs_name_shape():
    existing = {"upgradeAllowed": True, "cutoff": 100, "items": [{"quality": 11, "allowed": True}]}
    desired = {"upgradeAllowed": True, "cutoff": 100, "items": [{"quality": 11, "allowed": True}]}
    assert _profile_matches(existing, desired)
    desired["cutoff"] = 50
    assert not _profile_matches(existing, desired)
