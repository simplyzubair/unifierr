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
        "upload": mock.post(f"{U}/upload/plugin/file").respond(json={"success": True}),
        "flow": mock.post(f"{U}/plugins/flow").respond(json={"results": [
            {"plugin_id": "video_transcoder", "name": "T"}, {"plugin_id": "unifierr_verify", "name": "U"}]}),
        "flow_save": mock.post(f"{U}/plugins/flow/save").respond(json={"success": True}),
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
    assert lib["plugins"]["enabled_plugins"] == [{"library_id": 1, "plugin_id": "unifierr_verify"},
                                                 {"library_id": 1, "plugin_id": "video_transcoder"}]
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


async def test_safety_check_uploaded_with_jellyfin_details_and_ordered_around_the_encoder(mock):
    import io
    import zipfile

    r = routes(mock, installed=True, groups=[{"id": 1}])
    async with UnmanicAdapter(Connection(ServiceKind.unmanic, "http://unmanic:8888")) as a:
        await a.ensure_converter("/data/Movies", ("http://jellyfin:8096", "JKEY"))

    from email.parser import BytesParser

    upload = r["upload"].calls.last.request
    msg = BytesParser().parsebytes(b"Content-Type: " + upload.headers["content-type"].encode() + 2 * bytes([13, 10])
                                   + upload.content)
    z = zipfile.ZipFile(io.BytesIO(msg.get_payload()[0].get_payload(decode=True)))
    assert {"info.json", "plugin.py", "unifierr.json"} <= set(z.namelist())  # files at the zip root
    assert json.loads(z.read("unifierr.json")) == {"jellyfin_url": "http://jellyfin:8096", "jellyfin_api_key": "JKEY"}
    saves = [json.loads(c.request.content) for c in r["flow_save"].calls]
    order = {s["plugin_type"]: [p["plugin_id"] for p in s["plugin_flow"]] for s in saves}
    assert order["library_management.file_test"] == ["unifierr_verify", "video_transcoder"]
    assert order["worker.process"] == ["video_transcoder", "unifierr_verify"]
    assert saves[0]["plugin_flow"][0]["name"]  # full records, as Unmanic requires
    enabled = body(r["lib_write"])["plugins"]["enabled_plugins"]
    assert {p["plugin_id"] for p in enabled} == {"unifierr_verify", "video_transcoder"}


async def test_same_check_version_is_not_uploaded_again(mock):
    from app.adapters.unmanic import check_plugin_files

    version, _ = check_plugin_files(("http://jellyfin:8096", "JKEY"))
    r = routes(mock, installed=True, groups=[{"id": 1}])
    r["installed"].respond(json={"results": [{"plugin_id": "video_transcoder"},
                                             {"plugin_id": "unifierr_verify", "version": version}]})
    async with UnmanicAdapter(Connection(ServiceKind.unmanic, "http://unmanic:8888")) as a:
        await a.ensure_converter("/data/Movies", ("http://jellyfin:8096", "JKEY"))
    assert not r["upload"].called
    assert check_plugin_files(("http://jellyfin:8096", "NEWKEY"))[0] != version  # a new key forces a re-upload
