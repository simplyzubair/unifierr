"""Unmanic converter setup (payload shapes taken from a real Unmanic 0.4.1 instance)."""
import json

import httpx

from app.adapters.base import Connection, ServiceKind
from app.adapters.unmanic import TRANSCODE, UnmanicAdapter

U = "http://unmanic:8888/unmanic/api/v2"
PLUGIN_SETTINGS = [{"key_id": "a1", "key": k, "value": "x"} for k in TRANSCODE] + [
    {"key_id": "z9", "key": "unrelated", "value": "keep"}]


def routes(mock, *, installed: bool, groups: list):
    r = {
        "installed": mock.post(f"{U}/plugins/installed").respond(
            json={"results": [{"plugin_id": "video_transcoder"}] if installed else []}),
        "reload": mock.post(f"{U}/plugins/repos/reload").respond(json={"success": True}),
        "install": mock.post(f"{U}/plugins/install").respond(json={"success": True}),
        "libraries": mock.get(f"{U}/settings/libraries").respond(json={"libraries": [
            {"id": 1, "name": "x", "path": "/library", "enable_scanner": False, "enable_inotify": False,
             "priority_score": 0, "tags": []}]}),
        "lib_write": mock.post(f"{U}/settings/library/write").respond(json={"success": True}),
        "info": mock.post(f"{U}/plugins/info").respond(json={"settings": PLUGIN_SETTINGS}),
        "settings": mock.post(f"{U}/plugins/settings/update").respond(json={"success": True}),
        "groups": mock.get(f"{U}/settings/worker_groups").respond(json={"worker_groups": groups}),
        "group_write": mock.post(f"{U}/settings/worker_group/write").respond(json={"success": True}),
    }
    return r


def body(route):
    return json.loads(route.calls.last.request.content)


async def test_fresh_unmanic_is_fully_configured(mock):
    r = routes(mock, installed=False, groups=[])
    async with UnmanicAdapter(Connection(ServiceKind.unmanic, "http://unmanic:8888")) as a:
        await a.ensure_converter("/data/Movies")

    assert body(r["install"]) == {"plugin_id": "video_transcoder"}
    lib = body(r["lib_write"])
    assert lib["library_config"]["path"] == "/data/Movies" and lib["library_config"]["enable_inotify"] is True
    assert lib["plugins"]["enabled_plugins"] == [{"library_id": 1, "plugin_id": "video_transcoder"}]
    sent = {s["key"]: s["value"] for s in body(r["settings"])["settings"]}
    assert sent == TRANSCODE  # only our keys, never other plugin settings
    assert sent["target_resolution"] == "source" and sent["video_codec"] == "hevc"
    assert body(r["group_write"])["number_of_workers"] == 1


async def test_already_set_up_unmanic_is_not_duplicated(mock):
    r = routes(mock, installed=True, groups=[{"id": 1, "name": "Unifierr", "number_of_workers": 1}])
    async with UnmanicAdapter(Connection(ServiceKind.unmanic, "http://unmanic:8888")) as a:
        await a.ensure_converter("/library")
    assert not r["install"].called and not r["reload"].called and not r["group_write"].called


async def test_unmanic_error_reply_becomes_a_clear_error(mock):
    import pytest

    from app.core.errors import ServiceUnavailable

    mock.post(f"{U}/plugins/installed").mock(return_value=httpx.Response(
        200, json={"error": "400: Failed request schema validation"}))
    async with UnmanicAdapter(Connection(ServiceKind.unmanic, "http://unmanic:8888")) as a:
        with pytest.raises(ServiceUnavailable) as err:
            await a.ensure_converter("/library")
    assert "Unmanic refused" in err.value.message
