"""The safety-check plugin that runs inside Unmanic (plain stdlib module, tested directly)."""
import json

import pytest

from app.adapters import unmanic_verify_plugin as plugin


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin, "FAILED_LIST", str(tmp_path / "userdata" / "failed.json"))
    monkeypatch.setattr(plugin, "CONFIG_FILE", str(tmp_path / "unifierr.json"))
    monkeypatch.setattr(plugin.time, "sleep", lambda s: None)


def fake_probe(monkeypatch, codec="h264", bitrate=8_000_000, height=1080):
    monkeypatch.setattr(plugin, "ffprobe", lambda p: (
        {"bit_rate": str(bitrate), "duration": "100"}, [], [{"codec_name": codec, "height": height}]))


@pytest.mark.parametrize("codec", ["hevc", "av1", "vp9"])
def test_already_efficient_codecs_are_skipped(monkeypatch, codec):
    fake_probe(monkeypatch, codec=codec)
    assert plugin.skip_reason("/m.mkv") == f"already {codec.upper()}"


def test_lean_h264_is_skipped_but_heavy_h264_is_converted(monkeypatch):
    fake_probe(monkeypatch, bitrate=3_500_000, height=1080)
    assert "already small" in plugin.skip_reason("/m.mkv")
    fake_probe(monkeypatch, bitrate=8_000_000, height=1080)
    assert plugin.skip_reason("/m.mkv") is None
    fake_probe(monkeypatch, bitrate=8_000_000, height=2160)  # 8 Mbit/s is lean for 4K
    assert "already small" in plugin.skip_reason("/m.mkv")


def test_rejected_movie_is_never_queued_again(monkeypatch):
    fake_probe(monkeypatch)
    plugin._remember_failure("/m.mkv", "length changed")
    data = {"path": "/m.mkv"}
    plugin.on_library_management_file_test(data)
    assert data["add_file_to_pending_tasks"] is False


def test_failed_check_keeps_original(monkeypatch):
    monkeypatch.setattr(plugin, "problem", lambda o, c: "length changed from 100s to 60s")
    data = {"file_in": "/cache/m.mkv", "original_file_path": "/data/m.mkv", "worker_log": []}
    plugin.on_worker_process(data)
    assert data["exec_command"] == ["false"] and "original kept" in data["worker_log"][0]
    assert "/data/m.mkv" in json.load(open(plugin.FAILED_LIST, encoding="utf-8"))


def test_replacement_waits_while_someone_watches(monkeypatch):
    monkeypatch.setattr(plugin, "problem", lambda o, c: None)
    answers = iter([True, True, False])
    monkeypatch.setattr(plugin, "being_played", lambda p: next(answers))
    data = {"file_in": "/cache/m.mkv", "original_file_path": "/data/m.mkv", "worker_log": []}
    plugin.on_worker_process(data)
    assert data["exec_command"] == []  # passes: Unmanic may now replace the original
    assert any("waiting until they stop" in line for line in data["worker_log"])


def test_watched_for_a_whole_day_keeps_original_without_blacklisting(monkeypatch):
    monkeypatch.setattr(plugin, "problem", lambda o, c: None)
    monkeypatch.setattr(plugin, "being_played", lambda p: True)
    data = {"file_in": "/cache/m.mkv", "original_file_path": "/data/m.mkv", "worker_log": []}
    plugin.on_worker_process(data)
    assert data["exec_command"] == ["false"]
    assert plugin._failed() == {}  # retried on a later scan


def test_being_played_matches_by_file_name(monkeypatch):
    with open(plugin.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"jellyfin_url": "http://jf:8096", "jellyfin_api_key": "K"}, f)

    class Resp:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            import io
            return io.BytesIO(json.dumps(self.payload).encode())

        def __exit__(self, *a):
            return False

    seen = {}

    def urlopen(req, timeout):
        seen["auth"] = req.headers.get("Authorization")
        return Resp([{"NowPlayingItem": {"Path": "/media/Movies/Film (2020)/Film (2020).mkv"}}, {}])

    monkeypatch.setattr(plugin.urllib.request, "urlopen", urlopen)
    assert plugin.being_played("/data/Movies/Film (2020)/Film (2020).mkv") is True
    assert plugin.being_played("/data/Movies/Other/Other.mkv") is False
    assert seen["auth"] == 'MediaBrowser Token="K"'


def test_no_jellyfin_configured_means_not_playing():
    assert plugin.being_played("/data/x.mkv") is False


def test_temporary_part_files_are_ignored_without_probing(monkeypatch):
    monkeypatch.setattr(plugin, "ffprobe", lambda p: (_ for _ in ()).throw(AssertionError("must not probe")))
    assert "temporary" in plugin.skip_reason("/data/Movies/A/A.mkv.unmanic.part")
