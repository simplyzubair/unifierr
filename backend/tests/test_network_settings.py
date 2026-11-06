from app.adapters.base import HealthStatus, ServiceKind
from app.core.crypto import decrypt
from app.core.db import sessionmaker
from app.models import Setting
from app.services.common import set_settings
from app.services.health import vpn_issues
from app.services.installer import save_service
from tests.conftest import CSRF, make_admin


async def test_network_settings_encrypt_secrets_and_never_return_them(client):
    await make_admin(client)
    claim = "claim-never-return-this"
    password = "vpn-password-never-return-this"
    response = await client.put(
        "/api/settings",
        headers=CSRF,
        json={
            "vpn_enabled": True,
            "vpn_provider": "protonvpn",
            "vpn_type": "openvpn",
            "vpn_username": "vpn-user",
            "vpn_password": password,
            "plex_claim": claim,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["vpn_has_openvpn_credentials"] is True
    assert response.json()["plex_claim_saved"] is True
    assert claim not in response.text and password not in response.text

    async with sessionmaker()() as db:
        stored_claim = await db.get(Setting, "plex_claim_enc")
        stored_password = await db.get(Setting, "vpn_password_enc")
        assert stored_claim is not None and stored_claim.value != claim
        assert stored_password is not None and stored_password.value != password
        assert decrypt(stored_claim.value) == claim
        assert decrypt(stored_password.value) == password

    events = await client.get("/api/events")
    assert claim not in events.text and password not in events.text


async def test_enabled_vpn_requires_provider_credentials_without_echoing_input(client):
    await make_admin(client)
    response = await client.put(
        "/api/settings",
        headers=CSRF,
        json={"vpn_enabled": True, "vpn_provider": "protonvpn", "vpn_password": "do-not-echo"},
    )

    assert response.status_code == 400
    assert "VPN username and password" in response.json()["detail"]
    assert "do-not-echo" not in response.text


async def test_health_warns_when_download_client_is_not_using_gluetun(client):
    async with sessionmaker()() as db:
        await set_settings(db, {"vpn_enabled": True, "vpn_container_name": "gluetun"})
        qbit = await save_service(db, ServiceKind.qbittorrent, base_url="http://qbittorrent:8080")
        statuses = [(qbit, HealthStatus(ok=True, message="Connected"), [])]

        issues = await vpn_issues(db, statuses)
        assert issues and issues[0].severity == "warning"
        assert "Gluetun" in (issues[0].explanation or "")

        qbit.internal_url = "http://gluetun:8080"
        await db.commit()
        assert await vpn_issues(db, statuses) == []
