"""The safety-check plugin that runs inside Unmanic (plain stdlib module, tested directly)."""
import json

import pytest

from app.adapters import unmanic_verify_plugin as plugin


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin, "FAILED_LIST", str(tmp_path / "userdata" / "failed.json"))
    monkeypatch.setattr(plugin, "CONFIG_FILE", str(tmp_path / "unifierr.json"))
    monkeypatch.setattr(plugin.time, "sleep", lambda s: None)


def test_huge_disc_copies_are_shrunk_even_when_hevc(monkeypatch):
    fake_probe(monkeypatch, codec="hevc", bitrate=64_000_000, height=2160)
    assert plugin.skip_reason("/m.mkv") is None
    fake_probe(monkeypatch, codec="hevc", bitrate=32_000_000, height=2160)
    assert plugin.skip_reason("/m.mkv") == "already HEVC"


def _probe_pair(monkeypatch, before, after):
    base = {"duration": 100.0, "width": 3840, "height": 2160, "audio": 1, "subtitle": 1,
            "transfer": "smpte2084", "ten_bit": True}
    results = iter([{**base, **before}, {**base, **after}])
    monkeypatch.setattr(plugin, "probe", lambda path: next(results))
    monkeypatch.setattr(plugin, "decodes", lambda path, start: True)
    monkeypatch.setattr(plugin.os.path, "getsize", lambda path: 1 if "cache" in path else 2)


def test_copy_that_loses_hdr_or_10_bit_is_rejected(monkeypatch):
    _probe_pair(monkeypatch, {}, {"transfer": "bt709"})
    assert "HDR was lost" in plugin.problem("/data/m.mkv", "/cache/m.mkv")
    _probe_pair(monkeypatch, {}, {"ten_bit": False})
    assert "10-bit" in plugin.problem("/data/m.mkv", "/cache/m.mkv")
    _probe_pair(monkeypatch, {}, {})
    assert plugin.problem("/data/m.mkv", "/cache/m.mkv") is None


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


def test_being_played_asks_unifierr_with_the_token(monkeypatch):
    import io

    with open(plugin.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"unifierr_url": "http://unifierr:8484", "token": "T"}, f)
    seen = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout):
        seen["url"], seen["token"] = req.full_url, req.headers.get("X-unifierr-token")
        return Resp(json.dumps({"playing": True}).encode())

    monkeypatch.setattr(plugin.urllib.request, "urlopen", urlopen)
    assert plugin.being_played("/data/Movies/Film (2020)/Film (2020).mkv") is True
    assert seen["url"] == "http://unifierr:8484/api/converter/playing?name=Film+%282020%29.mkv"
    assert seen["token"] == "T"


def test_no_jellyfin_configured_means_not_playing():
    assert plugin.being_played("/data/x.mkv") is False


def test_temporary_part_files_are_ignored_without_probing(monkeypatch):
    monkeypatch.setattr(plugin, "ffprobe", lambda p: (_ for _ in ()).throw(AssertionError("must not probe")))
    assert "temporary" in plugin.skip_reason("/data/Movies/A/A.mkv.unmanic.part")
