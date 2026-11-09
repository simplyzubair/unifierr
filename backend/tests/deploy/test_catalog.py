from __future__ import annotations

from app.adapters.base import ServiceKind
from app.deploy.catalog import CATALOG


def test_catalog_contains_all_services() -> None:
    expected_kinds = {
        ServiceKind.radarr,
        ServiceKind.sonarr,
        ServiceKind.prowlarr,
        ServiceKind.qbittorrent,
        ServiceKind.sabnzbd,
        ServiceKind.nzbget,
        ServiceKind.bazarr,
        ServiceKind.jellyfin,
        ServiceKind.plex,
        ServiceKind.gluetun,
        ServiceKind.unmanic,
    }
    assert set(CATALOG.keys()) == expected_kinds

    for kind, spec in CATALOG.items():
        assert spec.kind == kind
        if kind == ServiceKind.gluetun:
            assert spec.image == "qmcgaw/gluetun:latest"
            assert spec.volumes == {}
            assert "NET_ADMIN" in spec.cap_add
            assert spec.devices == ["/dev/net/tun:/dev/net/tun"]
            assert spec.published_ports == {"6881/tcp": 6881, "6881/udp": 6881}
            continue
        # Unmanic has no linuxserver image; its own author publishes it on Docker Hub.
        assert spec.image.startswith("lscr.io/linuxserver/") or spec.image == "josh5/unmanic:latest"
        assert "{root}/data" in spec.volumes
        assert spec.volumes["{root}/data"] == "/data"
        assert f"{{appdata}}/{kind.value}" in spec.volumes
        assert spec.volumes[f"{{appdata}}/{kind.value}"] == "/config"
        assert "PUID" in spec.env
        assert "PGID" in spec.env
        assert "TZ" in spec.env
        assert spec.env.get("UMASK") == "002"
        assert len(spec.description) > 10


def test_catalog_qbittorrent_specifics() -> None:
    qbit = CATALOG[ServiceKind.qbittorrent]
    assert qbit.internal_port == 8080
    assert qbit.default_host_port == 8080
    assert qbit.env.get("WEBUI_PORT") == "8080"
    assert qbit.healthcheck_path == "/"


def test_catalog_healthcheck_paths() -> None:
    assert CATALOG[ServiceKind.radarr].healthcheck_path == "/ping"
    assert CATALOG[ServiceKind.sonarr].healthcheck_path == "/ping"
    assert CATALOG[ServiceKind.prowlarr].healthcheck_path == "/ping"
    assert CATALOG[ServiceKind.bazarr].healthcheck_path == "/"
    assert CATALOG[ServiceKind.jellyfin].healthcheck_path == "/health"
    assert CATALOG[ServiceKind.plex].healthcheck_path == "/identity"


def test_qbit_and_prowlarr_can_share_the_vpn_network() -> None:
    assert CATALOG[ServiceKind.qbittorrent].vpn_routed
    assert CATALOG[ServiceKind.prowlarr].vpn_routed
    assert not CATALOG[ServiceKind.radarr].vpn_routed
