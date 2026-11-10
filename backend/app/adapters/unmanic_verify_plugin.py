"""Unmanic plugin "unifierr_verify". This file is NOT imported by Unifierr: the Unmanic adapter uploads it to
Unmanic as the plugin's plugin.py. Standard library only (it runs inside the Unmanic container).

It runs after "Transcode Video Files" and only lets Unmanic replace the original movie when the converted copy is
complete and playable. On any doubt the task fails, so the original stays exactly as it was, and the movie is
remembered so it is not converted again.
"""
import json
import logging
import os
import subprocess
import time
import urllib.parse
import urllib.request

logger = logging.getLogger("Unmanic.Plugin.unifierr_verify")
# Kept in Unmanic's userdata folder, not the plugin folder, so reinstalling the plugin keeps the list.
# <unmanic>/plugins/unifierr_verify/plugin.py -> <unmanic>/userdata/unifierr_verify/failed.json
FAILED_LIST = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "userdata", "unifierr_verify", "failed.json")
SAMPLE_SECONDS = 10
# Written by Unifierr next to this file: {"unifierr_url": ..., "token": ...}. The token can only ask
# Unifierr "is this file being watched?"; no media-server key is ever stored here.
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "unifierr.json")
PLAYING_RECHECK_SECONDS = 60
MAX_PLAYING_WAIT_SECONDS = 24 * 3600


def _config() -> dict:
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def being_played(path: str) -> bool:
    """True while anyone streams this movie. Unifierr asks Jellyfin and matches by file name, because Jellyfin and
    Unmanic mount the media folder at different paths. If Unifierr cannot be asked, assume nobody is watching."""
    cfg = _config()
    url, token = cfg.get("unifierr_url"), cfg.get("token")
    if not url or not token:
        return False
    query = urllib.parse.urlencode({"name": os.path.basename(path)})
    request = urllib.request.Request(f"{url.rstrip('/')}/api/converter/playing?{query}",
                                     headers={"X-Unifierr-Token": token})
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return bool(json.load(resp).get("playing"))
    except (OSError, ValueError):
        return False


def _failed() -> dict:
    try:
        with open(FAILED_LIST, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _remember_failure(path: str, reason: str) -> None:
    failed = _failed()
    failed[path] = reason
    os.makedirs(os.path.dirname(FAILED_LIST), exist_ok=True)
    with open(FAILED_LIST, "w", encoding="utf-8") as f:
        json.dump(failed, f, indent=1)


def ffprobe(path: str) -> tuple[dict, list, list]:
    """(format, all streams, real video streams). Raises ValueError if the file cannot be read."""
    run = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                         capture_output=True, text=True, timeout=300)
    if run.returncode != 0:
        raise ValueError(f"cannot be opened ({run.stderr.strip()[:200] or 'ffprobe failed'})")
    data = json.loads(run.stdout or "{}")
    streams = data.get("streams") or []
    video = [s for s in streams if s.get("codec_type") == "video"
             and not (s.get("disposition") or {}).get("attached_pic")]
    if not video:
        raise ValueError("has no video stream")
    return data.get("format") or {}, streams, video


def probe(path: str) -> dict:
    """Duration, resolution and stream counts of a media file. Raises ValueError if it cannot be read."""
    fmt, streams, video = ffprobe(path)
    return {
        "duration": float(fmt.get("duration") or 0),
        "width": int(video[0].get("width") or 0),
        "height": int(video[0].get("height") or 0),
        "audio": sum(1 for s in streams if s.get("codec_type") == "audio"),
        "subtitle": sum(1 for s in streams if s.get("codec_type") == "subtitle"),
    }


def decodes(path: str, start: float) -> bool:
    run = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.0f}", "-i", path, "-t", str(SAMPLE_SECONDS),
                          "-f", "null", "-"], capture_output=True, text=True, timeout=900)
    return run.returncode == 0 and not run.stderr.strip()


def problem(original: str, converted: str) -> str | None:
    """Why the converted copy must not replace the original, or None when it is safe."""
    try:
        before, after = probe(original), probe(converted)
    except ValueError as exc:
        return f"converted file {exc}"
    if (after["width"], after["height"]) != (before["width"], before["height"]):
        return (f"resolution changed from {before['width']}x{before['height']} "
                f"to {after['width']}x{after['height']}")
    if abs(after["duration"] - before["duration"]) > max(2.0, before["duration"] * 0.01):
        return f"length changed from {before['duration']:.0f}s to {after['duration']:.0f}s"
    if after["audio"] < before["audio"]:
        return f"audio tracks dropped ({before['audio']} -> {after['audio']})"
    if after["subtitle"] < before["subtitle"]:
        return f"subtitles dropped ({before['subtitle']} -> {after['subtitle']})"
    end = max(0.0, after["duration"] - SAMPLE_SECONDS - 1)
    for start in sorted({0.0, end / 2, end}):
        if not decodes(converted, start):
            return f"picture or sound is damaged around {start:.0f}s"
    if os.path.getsize(converted) >= os.path.getsize(original):
        return "the converted file is not smaller"
    return None


# Already efficient codecs: re-encoding them to HEVC cannot make them meaningfully smaller (AV1 would even grow).
EFFICIENT_CODECS = {"hevc", "av1", "vp9"}
# Bitrate (bits/s) at or below which an older-codec file is already lean for its height; converting saves too
# little to be worth hours of CPU. Roughly what HEVC itself would produce at our quality setting.
LEAN_BITRATE = ((480, 1_000_000), (720, 2_000_000), (1080, 4_000_000), (1440, 7_000_000), (2160, 12_000_000))


def skip_reason(path: str) -> str | None:
    """Why this file should not be converted at all, or None to let the encoder decide."""
    if path.endswith((".part", ".tmp")):
        return "a temporary file (e.g. Unmanic's own copy being moved into place)"
    if path in _failed():
        return "an earlier conversion was rejected, original kept"
    try:
        fmt, _, video = ffprobe(path)
    except ValueError as exc:
        return str(exc)  # leave damaged or odd files alone
    codec = video[0].get("codec_name", "")
    if codec in EFFICIENT_CODECS:
        return f"already {codec.upper()}"
    bitrate = int(fmt.get("bit_rate") or 0)
    height = int(video[0].get("height") or 0)
    limit = next((rate for max_height, rate in LEAN_BITRATE if height <= max_height), LEAN_BITRATE[-1][1])
    if bitrate and bitrate <= limit:
        return f"already small ({bitrate / 1e6:.1f} Mbit/s for {height}p)"
    return None


def on_library_management_file_test(data):
    """Runs before the encoder's own test: Unmanic uses the first plugin that gives a yes/no answer."""
    reason = skip_reason(data.get("path", ""))
    if reason:
        data["add_file_to_pending_tasks"] = False
        logger.info("Not converting %s: %s", data.get("path"), reason)
    return data


def on_worker_process(data):
    data["exec_command"] = []
    data["repeat"] = False
    converted, original = data.get("file_in"), data.get("original_file_path")
    if not converted or not original or os.path.abspath(converted) == os.path.abspath(original):
        return data  # nothing was converted (e.g. already HEVC)
    reason = problem(original, converted)
    log = data.get("worker_log")
    if reason:
        logger.warning("Keeping original %s: %s", original, reason)
        if log is not None:
            log.append(f"\nUnifierr check FAILED, original kept unchanged: {reason}")
        _remember_failure(original, reason)
        data["exec_command"] = ["false"]  # fail the task: Unmanic then never replaces the original
        return data
    if log is not None:
        log.append("\nUnifierr check passed: playable, same resolution and length, all tracks kept, smaller.")
    # The original keeps playing while we wait; it is only swapped once nobody is watching it.
    waited = 0
    while being_played(original):
        if waited >= MAX_PLAYING_WAIT_SECONDS:
            if log is not None:
                log.append("\nStill being watched after 24 hours: original kept for now, will try again later.")
            data["exec_command"] = ["false"]  # not remembered as failed, so a later scan retries it
            return data
        if waited == 0 and log is not None:
            log.append("\nSomeone is watching this movie: waiting until they stop before replacing it.")
        time.sleep(PLAYING_RECHECK_SECONDS)
        waited += PLAYING_RECHECK_SECONDS
    return data
