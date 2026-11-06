from __future__ import annotations

from app.adapters.base import ServiceKind
from app.deploy.catalog import CATALOG


def test_catalog_contains_all_services() -> None:
    expected_kinds = {
        ServiceKind.radarr,
        ServiceKind.sonarr,
        ServiceKind.prowlarr,
        ServiceKind.qbittorrent,
        ServiceKind.bazarr,
        ServiceKind.jellyfin,
        ServiceKind.plex,
    }
    assert set(CATALOG.keys()) == expected_kinds

    for kind, spec in CATALOG.items():
        assert spec.kind == kind
        assert spec.image.startswith("lscr.io/linuxserver/")
        assert "{root}/data" in spec.volumes
        assert spec.volumes["{root}/data"] == "/data"
        assert f"{{appdata}}/{kind.value}" in spec.volumes
        assert spec.volumes[f"{{appdata}}/{kind.value}"] == "/config"
        assert "PUID" in spec.env
        assert "PGID" in spec.env
        assert "TZ" in spec.env
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
