"""Host environment and platform detection.

Detects platforms (Synology DSM, Unraid, TrueNAS, Linux, Windows, macOS)
using Docker daemon metadata, host mounts, and environment variables.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.deploy.docker_manager import DockerManager

PlatformType = Literal["synology", "unraid", "truenas", "linux", "windows", "macos", "unknown"]


class EnvironmentReport(BaseModel):
    platform: PlatformType
    in_container: bool
    docker_available: bool
    docker_version: str | None
    docker_error: str | None  # plain English why not available + fix
    suggested_root: str  # e.g. /volume1/docker/unifierr on Synology, /mnt/user/... on Unraid
    puid: int
    pgid: int
    timezone: str
    notes: list[str]  # platform-specific tips (plain English)


def detect_environment(
    docker: DockerManager,
    *,
    _fs_root: str | Path | None = None,
) -> EnvironmentReport:
    """Detect current operating platform, container status, and recommended storage paths."""
    fs_base = Path(_fs_root) if _fs_root else None

    def p(rel: str) -> Path:
        if fs_base is not None:
            return fs_base / rel
        return Path("/" + rel.lstrip("/"))

    in_container = p(".dockerenv").is_file() or Path("/.dockerenv").is_file()

    docker_available = docker.available()
    docker_version = docker.version() if docker_available else None
    docker_error = docker.error() if not docker_available else None
    docker_info = docker.info() if docker_available else {}

    # 1. Platform detection
    platform: PlatformType = "unknown"
    os_str = str(docker_info.get("OperatingSystem", "")).lower()

    if "synology" in os_str or "dsm" in os_str:
        platform = "synology"
    elif "unraid" in os_str:
        platform = "unraid"
    elif "truenas" in os_str:
        platform = "truenas"
    elif (
        p("etc/synoinfo.conf").is_file()
        or p("etc.defaults/synoinfo.conf").is_file()
        or p("volume1").is_dir()
    ):
        platform = "synology"
    elif p("etc/unraid-version").is_file() or p("boot/config").is_dir():
        platform = "unraid"
    elif (
        (p("etc/version").is_file() and "truenas" in p("etc/version").read_text(errors="ignore").lower())
        or p("etc/truenas-build-version").is_file()
        or (
            p("mnt").is_dir()
            and (p("usr/local/bin/midclt").is_file() or p("usr/bin/midclt").is_file())
        )
    ):
        platform = "truenas"
    elif sys.platform == "win32" and not in_container:
        platform = "windows"
    elif sys.platform == "darwin" and not in_container:
        platform = "macos"
    elif sys.platform.startswith("linux") or in_container:
        platform = "linux"

    # 2. Suggested root path
    env_root = os.environ.get("UNIFIERR_ROOT")
    if env_root and env_root.strip():
        suggested_root = env_root.strip()
    elif platform == "synology":
        suggested_root = "/volume1/docker/unifierr"
    elif platform == "unraid":
        suggested_root = "/mnt/user/unifierr"
    elif platform == "truenas":
        suggested_root = "/mnt/pool/unifierr"
        mnt_dir = p("mnt")
        if mnt_dir.is_dir():
            try:
                pools = [
                    d.name
                    for d in mnt_dir.iterdir()
                    if d.is_dir() and not d.name.startswith(".") and d.name not in ("user", "disks", "root")
                ]
                if pools:
                    suggested_root = f"/mnt/{pools[0]}/unifierr"
            except OSError:
                pass
    elif platform == "windows":
        suggested_root = "/srv/unifierr" if in_container else "C:/unifierr"
    elif platform == "macos":
        suggested_root = "/Users/Shared/unifierr"
    else:
        suggested_root = "/srv/unifierr"

    # 3. PUID / PGID
    puid_env = os.environ.get("PUID")
    if puid_env and puid_env.strip().isdigit():
        puid = int(puid_env.strip())
    elif hasattr(os, "getuid"):
        uid = os.getuid()
        puid = 1000 if uid == 0 else uid
    else:
        puid = 1000

    pgid_env = os.environ.get("PGID")
    if pgid_env and pgid_env.strip().isdigit():
        pgid = int(pgid_env.strip())
    elif hasattr(os, "getgid"):
        gid = os.getgid()
        pgid = 1000 if gid == 0 else gid
    else:
        pgid = 1000

    # 4. Timezone
    tz_env = os.environ.get("TZ")
    if tz_env and tz_env.strip():
        timezone = tz_env.strip()
    else:
        tz_file = p("etc/timezone")
        if tz_file.is_file():
            try:
                timezone = tz_file.read_text(encoding="utf-8").strip() or "UTC"
            except OSError:
                timezone = "UTC"
        else:
            timezone = "UTC"

    # 5. Beginner tips / notes per platform
    notes: list[str] = []
    if platform == "synology":
        notes.extend([
            "Run 'id' over SSH to find your DSM user's PUID and PGID so file permissions match.",
            "Keep all media and download folders under '/volume1' to enable instant atomic hardlinks.",
            "Verify the storage folder has read/write permissions for your DSM user.",
        ])
    elif platform == "unraid":
        notes.extend([
            "Use '/mnt/user/...' paths to span shares across your array and pool drives.",
            "Keep your appdata folder on a cache pool (SSD) for best database performance.",
            "Default Unraid user is typically nobody:users (PUID=99, PGID=100).",
        ])
    elif platform == "truenas":
        notes.extend([
            "Configure dataset ACL permissions to ensure your chosen PUID/PGID has read and write access.",
            "Keep your torrents and media folders inside the same dataset to allow hardlinks.",
        ])
    elif platform == "linux":
        notes.extend([
            "Ensure PUID and PGID match the regular Linux user who owns the media directory.",
            "Make sure your storage root resides on a single filesystem to allow hardlinks.",
        ])
    elif platform == "windows":
        notes.extend([
            "Running Docker via Windows. Hardlinks and Linux file permissions may behave differently.",
            "For 24/7 media automation, a dedicated Linux host or NAS is recommended.",
        ])
    elif platform == "macos":
        notes.extend([
            "Running Docker on macOS. Filesystem performance on mounted volumes may be slower than Linux.",
        ])
    else:
        notes.extend([
            "Ensure PUID and PGID match the directory owner and that media folders share a single filesystem.",
        ])

    return EnvironmentReport(
        platform=platform,
        in_container=in_container,
        docker_available=docker_available,
        docker_version=docker_version,
        docker_error=docker_error,
        suggested_root=suggested_root,
        puid=puid,
        pgid=pgid,
        timezone=timezone,
        notes=notes,
    )
