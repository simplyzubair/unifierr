from app.adapters.base import ServiceKind
from app.core.crypto import encrypt
from app.core.db import sessionmaker
from app.models import Service
from app.services import installer
from app.services.jobs import Job


class RecordingDocker:
    def __init__(self, containers=None):
        self.containers = containers or []
        self.install_args = []

    def list_containers(self, all=False):
        return self.containers

    def connect_network(self, *args):
        return None

    def install(self, spec, **kwargs):
        self.install_args.append((spec, kwargs))


async def _ready(*args, **kwargs):
    return True


async def test_install_plex_claim_is_decrypted_only_for_docker_env(client, monkeypatch, tmp_path):
    token = "claim-test-token"
    dm = RecordingDocker()
    monkeypatch.setattr(installer, "docker_manager", lambda: dm)
    monkeypatch.setattr(installer, "wait_until_up", _ready)
    settings = {
        "root": str(tmp_path), "puid": 1000, "pgid": 1000, "timezone": "UTC",
        "plex_claim_enc": encrypt(token), "vpn_enabled": False,
    }

    async with sessionmaker()() as db:
        job = Job(id="plex-install", kind="install")
        await installer.install_one(db, job, ServiceKind.plex, settings)
        service = await db.get(Service, 1)

    assert service is not None and service.kind == ServiceKind.plex.value
    _, options = dm.install_args[0]
    assert options["env_overrides"] == {"PLEX_CLAIM": token}
    assert token not in " ".join(job.log)


async def test_install_qbittorrent_uses_gluetun_network_and_url(client, monkeypatch, tmp_path):
    dm = RecordingDocker()
    monkeypatch.setattr(installer, "docker_manager", lambda: dm)
    monkeypatch.setattr(installer, "wait_until_up", _ready)
    monkeypatch.setattr("app.deploy.keys.preseed_qbittorrent", lambda *args: None)
    settings = {
        "root": str(tmp_path), "puid": 1000, "pgid": 1000, "timezone": "UTC",
        "vpn_enabled": True, "vpn_container_name": "custom-vpn",
    }

    async with sessionmaker()() as db:
        job = Job(id="qbit-install", kind="install")
        await installer.install_one(db, job, ServiceKind.qbittorrent, settings)
        service = await db.get(Service, 1)

    assert service is not None
    assert service.base_url == "http://custom-vpn:8080"
    assert dm.install_args[0][1]["network_mode"] == "container:custom-vpn"


async def test_install_gluetun_builds_provider_environment(client, monkeypatch, tmp_path):
    dm = RecordingDocker()
    monkeypatch.setattr(installer, "docker_manager", lambda: dm)
    settings = {
        "root": str(tmp_path), "puid": 1000, "pgid": 1000, "timezone": "UTC",
        "vpn_provider": "protonvpn", "vpn_type": "openvpn", "vpn_server_countries": "Switzerland",
        "vpn_username_enc": encrypt("vpn-user"), "vpn_password_enc": encrypt("vpn-password"),
    }

    async with sessionmaker()() as db:
        job = Job(id="gluetun-install", kind="install")
        await installer.install_one(db, job, ServiceKind.gluetun, settings)

    options = dm.install_args[0][1]
    assert options["env_overrides"]["VPN_SERVICE_PROVIDER"] == "protonvpn"
    assert options["env_overrides"]["OPENVPN_USER"] == "vpn-user"
    assert options["env_overrides"]["OPENVPN_PASSWORD"] == "vpn-password"
    assert options["env_overrides"]["SERVER_COUNTRIES"] == "Switzerland"
    assert "vpn-password" not in " ".join(job.log)
