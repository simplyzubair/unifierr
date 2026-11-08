"""HTTPX client that pins public DNS results before opening remote connections."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Collection
from typing import Any

import httpx

from app.core.service_url import (
    BLOCKED_HOSTS,
    BLOCKED_IPS,
    LOCAL_HOSTS,
    LOCAL_SUFFIXES,
    configured_service_hosts,
    is_ambiguous_numeric_host,
    is_local_service_address,
    is_tailnet_ip,
)


def _is_allowed_address(host: str, address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if host.lower().rstrip(".").endswith(".ts.net"):
        return is_tailnet_ip(address)
    return address.is_global


async def _resolve_public_address(host: str, port: int) -> str:
    """Resolve a remote service once and return a globally routable address."""
    loop = asyncio.get_running_loop()
    records = await loop.getaddrinfo(
        host,
        port,
        family=socket.AF_UNSPEC,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    addresses = list(dict.fromkeys(record[4][0] for record in records))
    if not addresses:
        raise OSError("The service hostname did not resolve.")

    parsed_addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise OSError("The service hostname resolved to an invalid address.") from exc
        if not _is_allowed_address(host, parsed):
            raise OSError("The service hostname resolved to a non-public address.")
        parsed_addresses.append(parsed)

    return str(parsed_addresses[0])


def _is_local_host(host: str) -> bool:
    lowered = host.lower().rstrip(".")
    try:
        address = ipaddress.ip_address(lowered)
        return is_local_service_address(address)
    except ValueError:
        return (
            lowered in LOCAL_HOSTS
            or lowered.endswith(LOCAL_SUFFIXES)
            or ("." not in lowered and lowered in configured_service_hosts())
        )


class SafeAsyncClient(httpx.AsyncClient):
    """Pin public service hostnames to prevent DNS changes between check and connect.

    Local names and IP literals keep their original URL. Remote hostnames are
    resolved immediately before each request, checked against non-public ranges,
    and replaced with the resolved IP. The original host remains in the Host
    header and TLS SNI so virtual hosting and certificate validation still work.
    Redirects are disabled because every redirect would need separate validation.
    """

    def __init__(
        self,
        *args: Any,
        trusted_local_hosts: Collection[str] = (),
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._trusted_local_hosts = frozenset(
            host.lower().rstrip(".") for host in trusted_local_hosts
        )

    async def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        kwargs["follow_redirects"] = False
        original_url = request.url
        original_host = request.url.host
        if original_host.lower().rstrip(".") in BLOCKED_HOSTS | BLOCKED_IPS:
            raise httpx.ConnectError("Metadata service addresses are not allowed.", request=request)
        try:
            literal_address = ipaddress.ip_address(original_host)
        except ValueError:
            literal_address = None
        had_host_header = "host" in request.headers
        original_host_header = request.headers.get("host")
        had_sni_extension = "sni_hostname" in request.extensions
        original_sni_extension = request.extensions.get("sni_hostname")
        rewritten = False

        if literal_address is None and is_ambiguous_numeric_host(original_host):
            raise httpx.ConnectError(
                "Ambiguous numeric service hostnames are not allowed.",
                request=request,
            )
        if literal_address is not None and (
            literal_address.is_link_local
            or literal_address.is_multicast
            or literal_address.is_unspecified
            or literal_address.is_reserved
            or (literal_address.is_loopback and original_host not in {"127.0.0.1", "::1"})
            or not literal_address.is_global and not is_local_service_address(literal_address)
        ):
            raise httpx.ConnectError("This service IP address is not allowed.", request=request)
        local_target = (
            _is_local_host(original_host)
            or original_host.lower().rstrip(".") in self._trusted_local_hosts
        )
        if literal_address is not None:
            local_target = literal_address.is_private or literal_address.is_loopback or is_tailnet_ip(literal_address)
        if request.url.scheme == "http" and not local_target:
            raise httpx.ConnectError("Remote service addresses must use HTTPS.", request=request)

        if request.url.scheme == "https" and not local_target:
            port = request.url.port or 443
            try:
                address = await _resolve_public_address(original_host, port)
            except OSError as exc:
                raise httpx.ConnectError(
                    "The remote service hostname could not be resolved to a public address.",
                    request=request,
                ) from exc

            request.url = request.url.copy_with(host=address)
            request.headers["Host"] = f"{original_host}:{port}"
            request.extensions["sni_hostname"] = original_host
            rewritten = True

        try:
            return await super().send(request, **kwargs)
        finally:
            if rewritten:
                # Restore the request URL before HTTPX handles cookies and
                # exposes the response request to callers.
                request.url = original_url
                if had_host_header:
                    request.headers["Host"] = original_host_header or ""
                else:
                    request.headers.pop("Host", None)
                if had_sni_extension:
                    request.extensions["sni_hostname"] = original_sni_extension
                else:
                    request.extensions.pop("sni_hostname", None)
