"""Detection and discovery of existing media services in Docker and on the network."""
from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel

from app.adapters.base import ServiceKind
from app.core.safe_http import SafeAsyncClient
from app.deploy.catalog import CATALOG
from app.deploy.docker_manager import ContainerInfo, DockerManager
from app.deploy.keys import read_arr_api_key, read_bazarr_api_key, read_nzbget_credentials, read_sabnzbd_api_key


class DetectedApp(BaseModel):
    kind: ServiceKind
    source: Literal["docker", "network"]
    container_name: str | None
    image: str | None
    url_candidates: list[str]  # ordered: best first (container name on shared network, host ip:port)
    reachable_url: str | None  # first candidate that answered
    config_path: str | None  # host path of /config mount, when readable
    api_key_found: bool
    managed: bool


def _match_kind(c: ContainerInfo) -> ServiceKind | None:
    img = c.image.lower()
    name = c.name.lower()

    if "gluetun" in img or "gluetun" in name:
        return ServiceKind.gluetun
    if "radarr" in img or "radarr" in name:
        return ServiceKind.radarr
    if "sonarr" in img or "sonarr" in name:
        return ServiceKind.sonarr
    if "prowlarr" in img or "prowlarr" in name:
        return ServiceKind.prowlarr
    if "qbittorrent" in img or "qbittorrent" in name or "qbit" in img or "qbit" in name:
        return ServiceKind.qbittorrent
    if "sabnzbd" in img or "sabnzbd" in name:
        return ServiceKind.sabnzbd
    if "nzbget" in img or "nzbget" in name:
        return ServiceKind.nzbget
    if "unmanic" in img or "unmanic" in name:
        return ServiceKind.unmanic
    if "bazarr" in img or "bazarr" in name:
        return ServiceKind.bazarr
    if "jellyfin" in img or "jellyfin" in name:
        return ServiceKind.jellyfin
    if ("plex" in img or "plex" in name or "pms-docker" in img) and not any(
        x in img or x in name
        for x in ("meta-manager", "tautulli", "trakt", "overseerr", "export", "connect", "auto")
    ):
        return ServiceKind.plex
    return None


def _is_safe_shared_container_host(name: str, networks: set[str], self_networks: set[str]) -> bool:
    """Trust only a simple Docker name on a network Unifierr can reach."""
    return bool(
        re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,127}", name.lower())
        and ("unifierr" in networks or bool(networks & self_networks))
    )


async def _probe_url(client: httpx.AsyncClient, url: str, healthcheck_path: str) -> bool:
    target = url.rstrip("/") + healthcheck_path
    with contextlib.suppress(Exception):  # noqa: BLE001
        resp = await client.get(target)
        if 200 <= resp.status_code < 400:
            return True
    return False


async def detect_apps(
    docker: DockerManager,
    *,
    probe_hosts: list[str] | None = None,
) -> list[DetectedApp]:
    """Discover running media apps in Docker containers and on the host network.

    Probes candidates with short HTTP timeouts to determine reachability and
    attempts to read API keys if the container's config folder is accessible.
    """
    detected: list[DetectedApp] = []
    detected_kinds: set[ServiceKind] = set()

    containers = docker.list_containers(all=False) if docker.available() else []
    self_c = docker.self_container()
    self_nets = set(self_c.networks) if self_c else set()
    trusted_local_hosts = {
        c.name.lower()
        for c in containers
        if _match_kind(c) in CATALOG
        and _is_safe_shared_container_host(c.name, set(c.networks), self_nets)
    }

    active_probe_hosts = (
        list(probe_hosts)
        if probe_hosts is not None
        else ["host.docker.internal", "localhost", "127.0.0.1"]
    )

    async with SafeAsyncClient(
        timeout=1.0,
        follow_redirects=False,
        trusted_local_hosts=trusted_local_hosts,
    ) as http_client:
        # 1. Inspect Docker containers
        for c in containers:
            kind = _match_kind(c)
            if not kind or kind not in CATALOG:
                continue

            spec = CATALOG[kind]
            if kind == ServiceKind.gluetun:
                detected.append(
                    DetectedApp(
                        kind=kind,
                        source="docker",
                        container_name=c.name,
                        image=c.image,
                        url_candidates=[],
                        reachable_url=None,
                        config_path=None,
                        api_key_found=False,
                        managed=c.labels.get("io.unifierr.managed") == "true",
                    )
                )
                detected_kinds.add(kind)
                continue
            internal_port = spec.internal_port
            container_nets = set(c.networks)
            shared_network = bool(
                "unifierr" in container_nets or (self_nets and (container_nets & self_nets))
            )

            candidates: list[str] = []
            container_name_url = f"http://{c.name}:{internal_port}"

            if shared_network:
                candidates.append(container_name_url)

            # Check published ports
            host_port = c.ports.get(internal_port)
            if host_port:
                for h in active_probe_hosts:
                    candidate = f"http://{h}:{host_port}"
                    if candidate not in candidates:
                        candidates.append(candidate)

            # Probe candidates in order
            reachable_url: str | None = None
            for candidate in candidates:
                if await _probe_url(http_client, candidate, spec.healthcheck_path):
                    reachable_url = candidate
                    break

            # Check config mount path
            config_path: str | None = None
            for m in c.mounts:
                if m.get("destination") == "/config":
                    config_path = m.get("source")
                    break

            # Attempt to read API key if config dir is accessible
            api_key_found = False
            if config_path and Path(config_path).is_dir():  # noqa: ASYNC240
                if kind in (ServiceKind.radarr, ServiceKind.sonarr, ServiceKind.prowlarr):
                    key = read_arr_api_key(config_path)
                    api_key_found = bool(key)
                elif kind == ServiceKind.bazarr:
                    key = read_bazarr_api_key(config_path)
                    api_key_found = bool(key)
                elif kind == ServiceKind.sabnzbd:
                    key = read_sabnzbd_api_key(config_path)
                    api_key_found = bool(key)
                elif kind == ServiceKind.nzbget:
                    _, password = read_nzbget_credentials(config_path)
                    api_key_found = bool(password)

            managed = c.labels.get("io.unifierr.managed") == "true"

            detected.append(
                DetectedApp(
                    kind=kind,
                    source="docker",
                    container_name=c.name,
                    image=c.image,
                    url_candidates=candidates,
                    reachable_url=reachable_url,
                    config_path=config_path,
                    api_key_found=api_key_found,
                    managed=managed,
                )
            )
            if reachable_url:
                detected_kinds.add(kind)

        # 2. Probe default ports on probe_hosts for non-Docker / native installs
        for kind, spec in CATALOG.items():
            if kind == ServiceKind.gluetun or kind in detected_kinds:
                continue

            for host in active_probe_hosts:
                candidate = f"http://{host}:{spec.default_host_port}"
                if await _probe_url(http_client, candidate, spec.healthcheck_path):
                    detected.append(
                        DetectedApp(
                            kind=kind,
                            source="network",
                            container_name=None,
                            image=None,
                            url_candidates=[candidate],
                            reachable_url=candidate,
                            config_path=None,
                            api_key_found=False,
                            managed=False,
                        )
                    )
                    detected_kinds.add(kind)
                    break

    return detected
