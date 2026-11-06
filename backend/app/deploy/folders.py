"""Folder management and disk validation for media storage layout.

Enforces TRaSH-guide storage structure where appdata, torrents, and media
co-exist on the same filesystem root to enable atomic hardlinks.
Never overwrites existing files or changes ownership of existing folders.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from pydantic import BaseModel

from app.adapters.base import HealthIssue


class FolderReport(BaseModel):
    root: str
    created: list[str]
    existing: list[str]
    writable: bool
    same_filesystem: bool  # hardlinks possible between torrents and media
    free_bytes: int
    total_bytes: int
    problems: list[HealthIssue]


_APPS = ("radarr", "sonarr", "prowlarr", "qbittorrent", "bazarr", "jellyfin", "plex")


def _expected_relative_dirs() -> list[str]:
    dirs = [
        "",
        "appdata",
        "data",
        "data/torrents",
        "data/torrents/movies",
        "data/torrents/tv",
        "data/media",
        "data/media/movies",
        "data/media/tv",
    ]
    for app in _APPS:
        dirs.append(f"appdata/{app}")
    return dirs


def prepare_folders(root: str, puid: int, pgid: int) -> FolderReport:
    """Create the storage layout and chown only newly created directories.

    Never touches permissions or files in existing folders.
    """
    root_path = Path(root).resolve()
    created: list[str] = []
    existing: list[str] = []
    problems: list[HealthIssue] = []

    is_root_user = hasattr(os, "geteuid") and os.geteuid() == 0

    for rel in _expected_relative_dirs():
        target = root_path / rel if rel else root_path
        target_str = target.as_posix()
        if target.is_dir():
            existing.append(target_str)
        else:
            try:
                target.mkdir(parents=True, exist_ok=True)
                created.append(target_str)
                # Only chown newly created directories, when running as root
                if hasattr(os, "chown") and is_root_user:
                    try:
                        os.chown(target, puid, pgid)
                    except OSError as chown_exc:
                        problems.append(
                            HealthIssue(
                                severity="warning",
                                message=f"Failed to set owner on {target_str}",
                                explanation=f"Could not chown to {puid}:{pgid}: {chown_exc}",
                                fix=f"Ensure root permissions or run 'chown -R {puid}:{pgid} {root}'.",
                                source="storage",
                            )
                        )
            except OSError as mkdir_exc:
                problems.append(
                    HealthIssue(
                        severity="error",
                        message=f"Failed to create folder {target_str}",
                        explanation=str(mkdir_exc),
                        fix=f"Check permissions of parent folder {root_path.parent}.",
                        source="storage",
                    )
                )

    writable = _check_writability(root_path, problems, puid, pgid)
    same_filesystem = _check_same_filesystem(root_path, problems)
    free_bytes, total_bytes = _check_disk_usage(root_path)

    return FolderReport(
        root=root,
        created=created,
        existing=existing,
        writable=writable,
        same_filesystem=same_filesystem,
        free_bytes=free_bytes,
        total_bytes=total_bytes,
        problems=problems,
    )


def check_folders(root: str) -> FolderReport:
    """Perform a read-only check of the storage folder layout and disk status."""
    root_path = Path(root).resolve()
    existing: list[str] = []
    problems: list[HealthIssue] = []

    if not root_path.is_dir():
        problems.append(
            HealthIssue(
                severity="error",
                message="Storage folder does not exist",
                explanation=f"The configured root directory '{root}' does not exist.",
                fix="Run folder setup in Settings -> Storage or create the folder.",
                source="storage",
            )
        )
        return FolderReport(
            root=root,
            created=[],
            existing=[],
            writable=False,
            same_filesystem=True,
            free_bytes=0,
            total_bytes=0,
            problems=problems,
        )

    for rel in _expected_relative_dirs():
        target = root_path / rel if rel else root_path
        if target.is_dir():
            existing.append(target.as_posix())

    writable = _check_writability(root_path, problems)
    same_filesystem = _check_same_filesystem(root_path, problems)
    free_bytes, total_bytes = _check_disk_usage(root_path)

    return FolderReport(
        root=root,
        created=[],
        existing=existing,
        writable=writable,
        same_filesystem=same_filesystem,
        free_bytes=free_bytes,
        total_bytes=total_bytes,
        problems=problems,
    )


def _check_writability(
    root_path: Path,
    problems: list[HealthIssue],
    puid: int | None = None,
    pgid: int | None = None,
) -> bool:
    test_file = root_path / ".unifierr_writetest"
    try:
        test_file.write_text("writetest", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        return True
    except OSError as exc:
        puid_str = f" (PUID={puid}, PGID={pgid})" if puid is not None else ""
        problems.append(
            HealthIssue(
                severity="error",
                message="Storage folder is not writable",
                explanation=(
                    f"Unifierr cannot write files to '{root_path.as_posix()}'. "
                    f"This usually occurs when host folder ownership does not match{puid_str}: {exc}"
                ),
                fix=f"Run 'chown -R {puid or 1000}:{pgid or 1000} {root_path.as_posix()}' on your host.",
                source="storage",
            )
        )
        return False


def _check_same_filesystem(root_path: Path, problems: list[HealthIssue]) -> bool:
    torrents_path = root_path / "data" / "torrents"
    media_path = root_path / "data" / "media"
    same_filesystem = True
    if torrents_path.is_dir() and media_path.is_dir():
        try:
            same_filesystem = torrents_path.stat().st_dev == media_path.stat().st_dev
        except OSError:
            same_filesystem = True

    if not same_filesystem:
        problems.append(
            HealthIssue(
                severity="warning",
                message="Torrents and media are on different filesystems",
                explanation=(
                    "Hardlinks cannot span multiple drives or filesystems. Completed downloads will be "
                    "copied rather than instantly linked, using double the disk space."
                ),
                fix="Ensure both torrents and media folders are on the same volume/disk share.",
                source="storage",
            )
        )
    return same_filesystem


def _check_disk_usage(root_path: Path) -> tuple[int, int]:
    try:
        usage = shutil.disk_usage(root_path)
        return usage.free, usage.total
    except OSError:
        return 0, 0
