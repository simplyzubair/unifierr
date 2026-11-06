from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.deploy.environment import detect_environment


def test_detect_environment_synology_fs(tmp_path: Path) -> None:
    # Simulate Synology filesystem markers
    (tmp_path / "etc").mkdir(parents=True)
    (tmp_path / "etc" / "synoinfo.conf").write_text("unique=synology_ds920+", encoding="utf-8")

    docker = MagicMock()
    docker.available.return_value = True
    docker.version.return_value = "24.0.7"
    docker.error.return_value = None
    docker.info.return_value = {"OperatingSystem": "Linux"}

    report = detect_environment(docker, _fs_root=tmp_path)
    assert report.platform == "synology"
    assert report.suggested_root == "/volume1/docker/unifierr"
    assert report.docker_available is True
    assert any("DSM" in note for note in report.notes)


def test_detect_environment_synology_docker_info(tmp_path: Path) -> None:
    docker = MagicMock()
    docker.available.return_value = True
    docker.version.return_value = "24.0.2"
    docker.error.return_value = None
    docker.info.return_value = {"OperatingSystem": "Synology DiskStation"}

    report = detect_environment(docker, _fs_root=tmp_path)
    assert report.platform == "synology"
    assert report.suggested_root == "/volume1/docker/unifierr"


def test_detect_environment_unraid(tmp_path: Path) -> None:
    (tmp_path / "etc").mkdir(parents=True)
    (tmp_path / "etc" / "unraid-version").write_text('version="6.12.4"', encoding="utf-8")

    docker = MagicMock()
    docker.available.return_value = True
    docker.version.return_value = "24.0.7"
    docker.error.return_value = None
    docker.info.return_value = {}

    report = detect_environment(docker, _fs_root=tmp_path)
    assert report.platform == "unraid"
    assert report.suggested_root == "/mnt/user/unifierr"
    assert any("cache pool" in note for note in report.notes)


def test_detect_environment_truenas(tmp_path: Path) -> None:
    (tmp_path / "etc").mkdir(parents=True)
    (tmp_path / "etc" / "version").write_text("TrueNAS-SCALE-23.10.1", encoding="utf-8")
    (tmp_path / "mnt" / "tank").mkdir(parents=True)

    docker = MagicMock()
    docker.available.return_value = True
    docker.version.return_value = "24.0.7"
    docker.error.return_value = None
    docker.info.return_value = {}

    report = detect_environment(docker, _fs_root=tmp_path)
    assert report.platform == "truenas"
    assert report.suggested_root == "/mnt/tank/unifierr"
    assert any("ACL" in note for note in report.notes)


def test_detect_environment_in_container_and_env_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Set /.dockerenv
    (tmp_path / ".dockerenv").touch()
    monkeypatch.setenv("UNIFIERR_ROOT", "/custom/storage/root")
    monkeypatch.setenv("PUID", "1005")
    monkeypatch.setenv("PGID", "1005")
    monkeypatch.setenv("TZ", "America/Chicago")

    docker = MagicMock()
    docker.available.return_value = False
    docker.error.return_value = "Socket not mounted"
    docker.version.return_value = None
    docker.info.return_value = {}

    report = detect_environment(docker, _fs_root=tmp_path)
    assert report.in_container is True
    assert report.docker_available is False
    assert report.docker_error == "Socket not mounted"
    assert report.suggested_root == "/custom/storage/root"
    assert report.puid == 1005
    assert report.pgid == 1005
    assert report.timezone == "America/Chicago"


def test_detect_environment_timezone_from_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TZ", raising=False)
    (tmp_path / "etc").mkdir(parents=True)
    (tmp_path / "etc" / "timezone").write_text("Europe/Paris\n", encoding="utf-8")

    docker = MagicMock()
    docker.available.return_value = True
    docker.version.return_value = "20.10.0"
    docker.error.return_value = None
    docker.info.return_value = {}

    report = detect_environment(docker, _fs_root=tmp_path)
    assert report.timezone == "Europe/Paris"
