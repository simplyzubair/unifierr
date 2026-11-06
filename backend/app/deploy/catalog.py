"""Application catalog defining container specifications for supported media services."""
from __future__ import annotations

from pydantic import BaseModel

from app.adapters.base import ServiceKind


class AppSpec(BaseModel):
    kind: ServiceKind
    display_name: str
    image: str
    container_name: str
    internal_port: int
    default_host_port: int
    volumes: dict[str, str]  # host template -> container path; templates use {root},{appdata}
    env: dict[str, str]  # may use {puid},{pgid},{tz}
    healthcheck_path: str  # HTTP path that returns 200/reachable when up
    description: str  # one beginner-friendly sentence


CATALOG: dict[ServiceKind, AppSpec] = {
    ServiceKind.radarr: AppSpec(
        kind=ServiceKind.radarr,
        display_name="Radarr",
        image="lscr.io/linuxserver/radarr:latest",
        container_name="radarr",
        internal_port=7878,
        default_host_port=7878,
        volumes={
            "{appdata}/radarr": "/config",
            "{root}/data": "/data",
        },
        env={
            "PUID": "{puid}",
            "PGID": "{pgid}",
            "TZ": "{tz}",
        },
        healthcheck_path="/ping",
        description="Automates movie downloading, sorting, and library management.",
    ),
    ServiceKind.sonarr: AppSpec(
        kind=ServiceKind.sonarr,
        display_name="Sonarr",
        image="lscr.io/linuxserver/sonarr:latest",
        container_name="sonarr",
        internal_port=8989,
        default_host_port=8989,
        volumes={
            "{appdata}/sonarr": "/config",
            "{root}/data": "/data",
        },
        env={
            "PUID": "{puid}",
            "PGID": "{pgid}",
            "TZ": "{tz}",
        },
        healthcheck_path="/ping",
        description="Automates TV series downloading, sorting, and episode tracking.",
    ),
    ServiceKind.prowlarr: AppSpec(
        kind=ServiceKind.prowlarr,
        display_name="Prowlarr",
        image="lscr.io/linuxserver/prowlarr:latest",
        container_name="prowlarr",
        internal_port=9696,
        default_host_port=9696,
        volumes={
            "{appdata}/prowlarr": "/config",
            "{root}/data": "/data",
        },
        env={
            "PUID": "{puid}",
            "PGID": "{pgid}",
            "TZ": "{tz}",
        },
        healthcheck_path="/ping",
        description="Indexer manager that connects torrent and Usenet indexers to Radarr and Sonarr.",
    ),
    ServiceKind.qbittorrent: AppSpec(
        kind=ServiceKind.qbittorrent,
        display_name="qBittorrent",
        image="lscr.io/linuxserver/qbittorrent:latest",
        container_name="qbittorrent",
        internal_port=8080,
        default_host_port=8080,
        volumes={
            "{appdata}/qbittorrent": "/config",
            "{root}/data": "/data",
        },
        env={
            "PUID": "{puid}",
            "PGID": "{pgid}",
            "TZ": "{tz}",
            "WEBUI_PORT": "8080",
        },
        healthcheck_path="/",
        description="Fast and lightweight torrent download client with a clean web management interface.",
    ),
    ServiceKind.bazarr: AppSpec(
        kind=ServiceKind.bazarr,
        display_name="Bazarr",
        image="lscr.io/linuxserver/bazarr:latest",
        container_name="bazarr",
        internal_port=6767,
        default_host_port=6767,
        volumes={
            "{appdata}/bazarr": "/config",
            "{root}/data": "/data",
        },
        env={
            "PUID": "{puid}",
            "PGID": "{pgid}",
            "TZ": "{tz}",
        },
        healthcheck_path="/",
        description="Companion application to Radarr and Sonarr for automatic subtitle downloading.",
    ),
    ServiceKind.jellyfin: AppSpec(
        kind=ServiceKind.jellyfin,
        display_name="Jellyfin",
        image="lscr.io/linuxserver/jellyfin:latest",
        container_name="jellyfin",
        internal_port=8096,
        default_host_port=8096,
        volumes={
            "{appdata}/jellyfin": "/config",
            "{root}/data": "/data",
        },
        env={
            "PUID": "{puid}",
            "PGID": "{pgid}",
            "TZ": "{tz}",
        },
        healthcheck_path="/health",
        description="Free and open-source media streaming server with no paywalls or tracking.",
    ),
    ServiceKind.plex: AppSpec(
        kind=ServiceKind.plex,
        display_name="Plex",
        image="lscr.io/linuxserver/plex:latest",
        container_name="plex",
        internal_port=32400,
        default_host_port=32400,
        volumes={
            "{appdata}/plex": "/config",
            "{root}/data": "/data",
        },
        env={
            "PUID": "{puid}",
            "PGID": "{pgid}",
            "TZ": "{tz}",
            "VERSION": "docker",
        },
        healthcheck_path="/identity",
        description="Popular media server streaming movies, TV shows, and music to any device.",
    ),
}
