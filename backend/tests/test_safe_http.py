from __future__ import annotations

import asyncio
import socket

import httpx
import pytest

from app.core.safe_http import SafeAsyncClient, _resolve_public_address


@pytest.mark.asyncio
async def test_remote_https_hostname_is_pinned_and_keeps_tls_identity(monkeypatch) -> None:
    loop = asyncio.get_running_loop()

    async def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
    requests: list[tuple[str, str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            (
                request.url.host,
                request.headers["host"],
                request.extensions["sni_hostname"],
            )
        )
        return httpx.Response(200)

    async with SafeAsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await client.get("https://media.example/api/status")

    assert response.status_code == 200
    assert len(requests) == 1
    assert requests[0] == ("93.184.216.34", "media.example:443", "media.example")
    assert response.request.url.host == "media.example"


@pytest.mark.asyncio
async def test_remote_hostname_resolving_to_private_address_is_rejected(monkeypatch) -> None:
    loop = asyncio.get_running_loop()

    async def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("192.168.1.20", 443))]

    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)

    async with SafeAsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as client:
        with pytest.raises(httpx.ConnectError, match="public address"):
            await client.get("https://media.example/api/status")


@pytest.mark.asyncio
async def test_local_container_hostname_is_not_public_dns_resolved(monkeypatch) -> None:
    loop = asyncio.get_running_loop()

    def unexpected_resolution(*args, **kwargs):
        raise AssertionError("local Docker hostnames must keep Docker DNS resolution")

    monkeypatch.setattr(loop, "getaddrinfo", unexpected_resolution)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "radarr"
        return httpx.Response(200)

    async with SafeAsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await client.get("http://radarr:7878/api/v3/system/status")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_remote_redirect_is_returned_without_following_it(monkeypatch) -> None:
    loop = asyncio.get_running_loop()

    async def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.host)
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    async with SafeAsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await client.get("https://media.example/api/status")

    assert response.status_code == 302
    assert requests == ["93.184.216.34"]
    assert response.request.url.host == "media.example"


@pytest.mark.asyncio
async def test_resolver_rejects_non_global_answers(monkeypatch) -> None:
    loop = asyncio.get_running_loop()

    async def fake_getaddrinfo(*args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.5", 443)),
        ]

    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(OSError, match="non-public"):
        await _resolve_public_address("media.example", 443)


@pytest.mark.asyncio
async def test_resolver_allows_tailscale_magicdns_cgnat_answer(monkeypatch) -> None:
    loop = asyncio.get_running_loop()

    async def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("100.100.100.20", 443))]

    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)

    assert await _resolve_public_address("synology-nas.tail594efe.ts.net", 443) == "100.100.100.20"


@pytest.mark.asyncio
async def test_resolver_rejects_cgnat_for_non_tailscale_hostname(monkeypatch) -> None:
    loop = asyncio.get_running_loop()

    async def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("100.100.100.20", 443))]

    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(OSError, match="non-public"):
        await _resolve_public_address("media.example", 443)


@pytest.mark.asyncio
async def test_safe_client_rejects_ambiguous_numeric_https_host() -> None:
    async with SafeAsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as client:
        with pytest.raises(httpx.ConnectError, match="Ambiguous numeric"):
            await client.get("https://2130706433/api/status")


@pytest.mark.asyncio
async def test_safe_client_allows_tailscale_ip_literal() -> None:
    async with SafeAsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as client:
        response = await client.get("https://100.64.0.1/api/status")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_safe_client_rejects_remote_http_service() -> None:
    async with SafeAsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as client:
        with pytest.raises(httpx.ConnectError, match="must use HTTPS"):
            await client.get("http://media.example/api/status")
