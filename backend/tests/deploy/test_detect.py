from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import respx

from app.adapters.base import ServiceKind
from app.deploy.detect import detect_apps
from app.deploy.docker_manager import ContainerInfo, DockerManager
from app.deploy.keys import preseed_arr_config


@pytest.mark.asyncio
async def test_detect_docker_matching_and_key_reading(tmp_path: Path) -> None:
    # Set up config directory with preseeded radarr key
    config_dir = tmp_path / "radarr_cfg"
    preseed_arr_config(str(config_dir), "fake_radarr_api_key_1234567890", 7878)

    containers = [
        ContainerInfo(
            id="c1",
            name="my-radarr",
            image="linuxserver/radarr:latest",
            status="running",
            health="healthy",
            ports={7878: 7878},
            networks=["unifierr"],
            mounts=[{"source": str(config_dir), "destination": "/config"}],
            labels={"io.unifierr.managed": "true"},
        ),
        ContainerInfo(
            id="c2",
            name="custom-sonarr-box",
            image="ghcr.io/hotio/sonarr:release",
            status="running",
            health=None,
            ports={8989: 8989},
            networks=["bridge"],
            mounts=[],
            labels={},
        ),
    ]

    mock_dm = MagicMock(spec=DockerManager)
    mock_dm.available.return_value = True
    mock_dm.list_containers.return_value = containers
    mock_dm.self_container.return_value = None

    with respx.mock(assert_all_called=False) as respx_mock:
        # Mock healthcheck probe for radarr and sonarr
        respx_mock.get("http://my-radarr:7878/ping").respond(200, text="OK")
        respx_mock.get("http://localhost:8989/ping").respond(200, text="OK")

        apps = await detect_apps(mock_dm, probe_hosts=["localhost"])

    assert len(apps) >= 2
    radarr_app = next(a for a in apps if a.kind == ServiceKind.radarr)
    assert radarr_app.source == "docker"
    assert radarr_app.container_name == "my-radarr"
    assert radarr_app.reachable_url == "http://my-radarr:7878"
    assert radarr_app.config_path == str(config_dir)
    assert radarr_app.api_key_found is True
    assert radarr_app.managed is True

    sonarr_app = next(a for a in apps if a.kind == ServiceKind.sonarr)
    assert sonarr_app.source == "docker"
    assert sonarr_app.container_name == "custom-sonarr-box"
    assert sonarr_app.managed is False


@pytest.mark.asyncio
async def test_detect_network_apps() -> None:
    mock_dm = MagicMock(spec=DockerManager)
    mock_dm.available.return_value = False
    mock_dm.list_containers.return_value = []
    mock_dm.self_container.return_value = None

    with respx.mock(assert_all_called=False) as respx_mock:
        # Simulate Bazarr answering on host port 6767
        respx_mock.get("http://127.0.0.1:6767/").respond(200, text="Bazarr WebUI")

        apps = await detect_apps(mock_dm, probe_hosts=["127.0.0.1"])

    bazarr_app = next((a for a in apps if a.kind == ServiceKind.bazarr), None)
    assert bazarr_app is not None
    assert bazarr_app.source == "network"
    assert bazarr_app.reachable_url == "http://127.0.0.1:6767"
    assert bazarr_app.managed is False
    assert bazarr_app.container_name is None


@pytest.mark.asyncio
async def test_detect_gluetun_container_without_http_probe() -> None:
    gluetun = ContainerInfo(
        id="vpn1",
        name="secure-vpn",
        image="qmcgaw/gluetun:latest",
        status="running",
        health="healthy",
        ports={8080: 8080},
        networks=["unifierr"],
        mounts=[],
        labels={"io.unifierr.managed": "true"},
    )
    mock_dm = MagicMock(spec=DockerManager)
    mock_dm.available.return_value = True
    mock_dm.list_containers.return_value = [gluetun]
    mock_dm.self_container.return_value = None

    apps = await detect_apps(mock_dm, probe_hosts=["localhost"])

    detected = next(app for app in apps if app.kind == ServiceKind.gluetun)
    assert detected.container_name == "secure-vpn"
    assert detected.reachable_url is None
    assert detected.managed is True
