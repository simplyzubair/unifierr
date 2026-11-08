"""Validation for user-configured integration endpoints."""

from __future__ import annotations

import ipaddress
import os
import re
from urllib.parse import urlsplit

BLOCKED_HOSTS = frozenset({"metadata", "metadata.google.internal", "metadata.google"})
BLOCKED_IPS = frozenset({"100.100.100.200", "fd00:ec2::254"})
LOCAL_SUFFIXES = (".local", ".lan", ".home.arpa", ".internal", ".localhost")
LOCAL_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "host.docker.internal",
        "radarr",
        "sonarr",
        "prowlarr",
        "qbittorrent",
        "qbt",
        "sabnzbd",
        "nzbget",
        "bazarr",
        "jellyfin",
        "plex",
        "gluetun",
    }
)
TAILSCALE_NETWORKS = (
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("fd7a:115c:a1e0::/48"),
)
PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)


def configured_service_hosts() -> frozenset[str]:
    """Read exact external hosts explicitly trusted by the server operator."""
    hosts: set[str] = set()
    for item in os.environ.get("UNIFIERR_ALLOWED_SERVICE_HOSTS", "").split(","):
        host = item.strip().lower().rstrip(".")
        if not host or "*" in host or "/" in host or "@" in host:
            continue
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if len(host) > 253 or not re.fullmatch(r"[a-z0-9.-]+", host):
                continue
            if any(not label or len(label) > 63 for label in host.split(".")):
                continue
        hosts.add(host)
    return frozenset(hosts)


def is_tailnet_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(address.version == network.version and address in network for network in TAILSCALE_NETWORKS)


def is_local_service_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        address.is_loopback
        or is_tailnet_ip(address)
        or any(address.version == network.version and address in network for network in PRIVATE_NETWORKS)
    )


def is_ambiguous_numeric_host(hostname: str) -> bool:
    """Detect malformed numeric hosts interpreted inconsistently by network stacks."""
    lowered = hostname.lower().rstrip(".")
    try:
        ipaddress.ip_address(lowered)
    except ValueError:
        pass
    else:
        return False
    if lowered.startswith("0x") and len(lowered) > 2:
        return all(char in "0123456789abcdef." for char in lowered[2:])
    return bool(lowered) and all(char.isdigit() or char == "." for char in lowered)


def is_local_service_host(hostname: str) -> bool:
    """Return true only for known local names and private IP literals."""
    lowered = hostname.lower().rstrip(".")
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        return (
            lowered in LOCAL_HOSTS
            or lowered.endswith(LOCAL_SUFFIXES)
            or ("." not in lowered and lowered in configured_service_hosts())
        )
    return is_local_service_address(address)


def validate_service_url(value: str) -> str:
    """Allow known local/Tailscale services and exact operator-approved HTTPS hosts."""
    if not value or any(ord(char) < 32 for char in value):
        raise ValueError("Enter a valid service address.")

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("Enter a valid service address.") from exc

    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use an HTTP or HTTPS address without embedded credentials, query, or fragment.")

    host = hostname.lower().rstrip(".")
    if host in BLOCKED_HOSTS or host in BLOCKED_IPS or is_ambiguous_numeric_host(host):
        raise ValueError("Use a standard IP address instead of an ambiguous numeric host.")

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None

    if address is not None:
        if (
            address.is_link_local
            or address.is_multicast
            or address.is_unspecified
            or address.is_reserved
            or (address.is_loopback and host not in {"127.0.0.1", "::1"})
        ):
            raise ValueError("Link-local, multicast, reserved, and unspecified addresses are not allowed.")
        local = is_local_service_address(address)
        approved = host in configured_service_hosts()
        if not local and not approved:
            raise ValueError("For safety, add this exact public host to UNIFIERR_ALLOWED_SERVICE_HOSTS first.")
        if not local and parsed.scheme != "https":
            raise ValueError("Use HTTPS for an approved public service address.")
    else:
        local = is_local_service_host(host)
        tailscale = host.endswith(".ts.net")
        approved = host in configured_service_hosts()
        if not local and not tailscale and not approved:
            raise ValueError("For safety, add this exact public host to UNIFIERR_ALLOWED_SERVICE_HOSTS first.")
        if not local and parsed.scheme != "https":
            raise ValueError("Use HTTPS for Tailscale or approved public service addresses.")

    return value.rstrip("/")
