from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.deploy.folders import check_folders, prepare_folders


def test_prepare_folders_creates_trash_layout(tmp_path: Path) -> None:
    root = str(tmp_path / "storage")
    report = prepare_folders(root, puid=1000, pgid=1000)

    assert report.root == root
    assert report.writable is True
    assert report.same_filesystem is True
    assert len(report.created) > 0
    assert len(report.existing) == 0

    # Verify directory structure exists
    root_p = Path(root)
    assert (root_p / "appdata" / "radarr").is_dir()
    assert (root_p / "appdata" / "sonarr").is_dir()
    assert (root_p / "appdata" / "qbittorrent").is_dir()
    assert (root_p / "data" / "torrents" / "movies").is_dir()
    assert (root_p / "data" / "torrents" / "tv").is_dir()
    assert (root_p / "data" / "media" / "movies").is_dir()
    assert (root_p / "data" / "media" / "tv").is_dir()


def test_prepare_folders_no_overwrite_existing(tmp_path: Path) -> None:
    root = str(tmp_path / "storage")
    root_p = Path(root)

    # Pre-create a folder
    pre_existing = root_p / "appdata" / "radarr"
    pre_existing.mkdir(parents=True, exist_ok=True)

    report = prepare_folders(root, puid=1000, pgid=1000)

    # Pre-existing folder should be reported in existing, not created
    assert pre_existing.as_posix() in report.existing
    assert pre_existing.as_posix() not in report.created


def test_check_folders_read_only(tmp_path: Path) -> None:
    root = str(tmp_path / "storage_check")

    # Check non-existent folder
    report_missing = check_folders(root)
    assert report_missing.writable is False
    assert any("does not exist" in p.message for p in report_missing.problems)

    # Now create layout and re-check
    prepare_folders(root, puid=1000, pgid=1000)
    report_ok = check_folders(root)
    assert report_ok.writable is True
    assert len(report_ok.existing) >= 10
    assert len(report_ok.created) == 0  # check_folders never creates folders
    assert len(report_ok.problems) == 0


def test_folders_unwritable_detection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = str(tmp_path / "storage_unwritable")
    prepare_folders(root, puid=1000, pgid=1000)

    # Mock writetest to raise PermissionError
    def fake_write_text(self, *args, **kwargs):
        raise PermissionError("Permission denied: simulated read-only mount")

    monkeypatch.setattr(Path, "write_text", fake_write_text)

    report = check_folders(root)
    assert report.writable is False
    assert any(p.severity == "error" and "not writable" in p.message.lower() for p in report.problems)


def test_folders_different_filesystems_detection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = str(tmp_path / "storage_diff_fs")
    prepare_folders(root, puid=1000, pgid=1000)

    orig_stat = Path.stat

    def fake_stat(self, *args, **kwargs):
        st = orig_stat(self, *args, **kwargs)
        # Simulate different device ID for media vs torrents
        if "media" in str(self):
            return os.stat_result((
                st.st_mode,
                st.st_ino,
                st.st_dev + 1,  # different filesystem
                st.st_nlink,
                st.st_uid,
                st.st_gid,
                st.st_size,
                st.st_atime,
                st.st_mtime,
                st.st_ctime,
            ))
        return st

    monkeypatch.setattr(Path, "stat", fake_stat)

    report = check_folders(root)
    assert report.same_filesystem is False
    assert any("different filesystems" in p.message.lower() for p in report.problems)
