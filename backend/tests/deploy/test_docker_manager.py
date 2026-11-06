from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.adapters.base import ServiceKind
from app.core.errors import UnifierrError
from app.deploy.catalog import CATALOG
from app.deploy.docker_manager import DockerManager


def test_docker_manager_lazy_init_and_socket_error() -> None:
    # Init with non-existent host should not raise immediately
    dm = DockerManager(docker_host="unix:///non/existent/docker.sock")
    assert dm.available() is False
    err = dm.error()
    assert err is not None
    assert "/var/run/docker.sock:/var/run/docker.sock" in err


def test_docker_manager_permission_error() -> None:
    mock_client = MagicMock()
    mock_client.ping.side_effect = PermissionError("Permission denied: /var/run/docker.sock")

    dm = DockerManager(client=mock_client)
    assert dm.available() is False
    assert "Permission denied" in (dm.error() or "")


def test_docker_manager_install_refuses_existing() -> None:
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_client.containers.get.return_value = mock_container

    dm = DockerManager(client=mock_client)
    spec = CATALOG[ServiceKind.radarr]

    with pytest.raises(UnifierrError) as exc_info:
        dm.install(spec, root="/srv/unifierr", puid=1000, pgid=1000, tz="UTC")

    assert "already exists" in str(exc_info.value)
    mock_client.containers.create.assert_not_called()


def test_docker_manager_install_success() -> None:
    mock_client = MagicMock()
    # Container does not exist initially
    mock_client.containers.get.side_effect = Exception("Not found")

    # API pull stream
    mock_client.api.pull.return_value = [
        {"status": "Downloading", "progressDetail": {"current": 50, "total": 100}},
        {"status": "Download complete"},
    ]

    created_container = MagicMock()
    created_container.id = "c123456"
    created_container.name = "radarr"
    created_container.image = "lscr.io/linuxserver/radarr:latest"
    created_container.status = "running"
    created_container.attrs = {
        "Config": {"Image": "lscr.io/linuxserver/radarr:latest", "Labels": {"io.unifierr.managed": "true"}},
        "State": {"Status": "running"},
        "NetworkSettings": {"Ports": {"7878/tcp": [{"HostPort": "7878"}]}, "Networks": {"unifierr": {}}},
        "Mounts": [{"Source": "/srv/unifierr/data", "Destination": "/data"}],
    }
    mock_client.containers.create.return_value = created_container

    progress_messages: list[str] = []
    dm = DockerManager(client=mock_client)
    spec = CATALOG[ServiceKind.radarr]

    info = dm.install(
        spec,
        root="/srv/unifierr",
        puid=1000,
        pgid=1000,
        tz="UTC",
        progress=progress_messages.append,
    )

    assert info.name == "radarr"
    assert info.ports.get(7878) == 7878
    assert any("50%" in msg for msg in progress_messages)
    mock_client.containers.create.assert_called_once()
    created_container.start.assert_called_once()


def test_docker_manager_update_refuses_unmanaged() -> None:
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.labels = {}
    mock_container.attrs = {"Config": {"Labels": {}}}
    mock_client.containers.get.return_value = mock_container

    dm = DockerManager(client=mock_client)
    with pytest.raises(UnifierrError) as exc_info:
        dm.update("unmanaged_radarr")

    assert "not managed by Unifierr" in str(exc_info.value)


def test_docker_manager_update_success() -> None:
    mock_client = MagicMock()
    old_c = MagicMock()
    old_c.name = "radarr"
    old_c.labels = {"io.unifierr.managed": "true", "io.unifierr.kind": "radarr"}
    old_c.attrs = {
        "Config": {
            "Image": "lscr.io/linuxserver/radarr:latest",
            "Env": ["PUID=1000", "PGID=1000"],
            "Labels": {"io.unifierr.managed": "true"},
        },
        "HostConfig": {
            "Binds": ["/srv/unifierr/data:/data:rw"],
            "PortBindings": {"7878/tcp": [{"HostPort": "7878"}]},
            "RestartPolicy": {"Name": "unless-stopped"},
        },
        "NetworkSettings": {"Networks": {"unifierr": {}}},
    }
    mock_client.containers.get.return_value = old_c
    mock_client.api.pull.return_value = [{"status": "Already up to date"}]

    new_c = MagicMock()
    new_c.id = "c_new_999"
    new_c.name = "radarr"
    new_c.image = "lscr.io/linuxserver/radarr:latest"
    new_c.status = "running"
    new_c.attrs = old_c.attrs
    mock_client.containers.create.return_value = new_c

    dm = DockerManager(client=mock_client)
    info = dm.update("radarr")

    assert info.name == "radarr"
    old_c.stop.assert_called_once()
    old_c.rename.assert_called_with("radarr-old")
    new_c.start.assert_called_once()
    old_c.remove.assert_called_with(force=True)


def test_docker_manager_update_rollback_on_failure() -> None:
    mock_client = MagicMock()
    old_c = MagicMock()
    old_c.name = "radarr"
    old_c.labels = {"io.unifierr.managed": "true"}
    old_c.attrs = {
        "Config": {"Image": "lscr.io/linuxserver/radarr:latest", "Labels": {"io.unifierr.managed": "true"}},
        "HostConfig": {"Binds": [], "PortBindings": {}, "RestartPolicy": {"Name": "unless-stopped"}},
        "NetworkSettings": {"Networks": {"unifierr": {}}},
    }
    mock_client.containers.get.return_value = old_c
    mock_client.api.pull.return_value = []

    # Simulate creation failure of new container
    mock_client.containers.create.side_effect = RuntimeError("Port already allocated: 7878")

    dm = DockerManager(client=mock_client)
    with pytest.raises(UnifierrError) as exc_info:
        dm.update("radarr")

    assert "rolled back successfully" in str(exc_info.value)
    # Verify rollback steps
    old_c.rename.assert_any_call("radarr")
    old_c.start.assert_called()


def test_install_port_clash_removes_half_created_container() -> None:
    mock_client = MagicMock()
    mock_client.containers.get.side_effect = Exception("Not found")
    mock_client.api.pull.return_value = []
    created = MagicMock()
    created.start.side_effect = Exception("Bind for 0.0.0.0:8080 failed: port is already allocated")
    mock_client.containers.create.return_value = created

    dm = DockerManager(client=mock_client)
    with pytest.raises(UnifierrError) as err:
        dm.install(CATALOG[ServiceKind.qbittorrent], root="/srv/unifierr", puid=1000, pgid=1000, tz="UTC")
    assert "8080" in err.value.message and err.value.fix
    created.remove.assert_called_once_with(force=True)


def test_install_gluetun_capabilities_and_published_ports() -> None:
    mock_client = MagicMock()
    mock_client.containers.get.side_effect = Exception("Not found")
    mock_client.api.pull.return_value = []
    created = MagicMock()
    created.id = "vpn1"
    created.name = "gluetun"
    created.image = "qmcgaw/gluetun:latest"
    created.status = "running"
    created.attrs = {
        "Config": {"Image": "qmcgaw/gluetun:latest", "Labels": {"io.unifierr.managed": "true"}},
        "State": {"Status": "running"},
        "NetworkSettings": {"Ports": {}, "Networks": {"unifierr": {}}},
        "Mounts": [],
    }
    mock_client.containers.create.return_value = created

    DockerManager(client=mock_client).install(
        CATALOG[ServiceKind.gluetun], root="/srv/unifierr", puid=1000, pgid=1000, tz="UTC",
    )

    options = mock_client.containers.create.call_args.kwargs
    assert options["ports"]["8080/tcp"] == 8080
    assert options["ports"]["6881/udp"] == 6881
    assert options["cap_add"] == ["NET_ADMIN"]
    assert options["devices"] == ["/dev/net/tun:/dev/net/tun"]
    assert options["volumes"] == {}


def test_install_vpn_routed_client_uses_shared_network_and_redacts_env_secret() -> None:
    token = "claim-secret-that-must-not-appear"
    mock_client = MagicMock()
    mock_client.containers.get.side_effect = Exception("Not found")
    mock_client.api.pull.return_value = []
    mock_client.containers.create.side_effect = RuntimeError(f"Docker rejected {token}")

    with pytest.raises(UnifierrError) as exc_info:
        DockerManager(client=mock_client).install(
            CATALOG[ServiceKind.qbittorrent], root="/srv/unifierr", puid=1000, pgid=1000, tz="UTC",
            network_mode="container:gluetun", env_overrides={"VPN_PASSWORD": token},
        )

    options = mock_client.containers.create.call_args.kwargs
    assert options["network_mode"] == "container:gluetun"
    assert options["ports"] == {}
    assert "network" not in options
    assert options["environment"]["VPN_PASSWORD"] == token
    assert token not in str(exc_info.value)


def test_restart_refuses_unmanaged_container() -> None:
    mock_client = MagicMock()
    c = MagicMock()
    c.labels = {}
    mock_client.containers.get.return_value = c
    with pytest.raises(UnifierrError):
        DockerManager(client=mock_client).restart("someones-radarr")
    c.restart.assert_not_called()
