import pytest

from app.core.service_url import validate_service_url


@pytest.mark.parametrize("url", [
    "http://radarr:7878",
    "http://192.168.1.20:8096",
    "https://synology-nas.tail594efe.ts.net:8920",
    "http://localhost:8096",
    "http://host.docker.internal:8096",
    "http://jellyfin.local:8096",
])
def test_allows_local_services_and_secure_remote_services(url):
    assert validate_service_url(url) == url


def test_allows_only_exact_operator_approved_public_host(monkeypatch):
    monkeypatch.setenv("UNIFIERR_ALLOWED_SERVICE_HOSTS", "media.example.com")
    assert validate_service_url("https://media.example.com:8920") == "https://media.example.com:8920"


@pytest.mark.parametrize("url", [
    "https://attacker.example.com:8096",
    "https://media.example.com:8920",
    "http://custom-radarr:7878",
    "https://203.0.113.10:8096",
])
def test_rejects_unapproved_public_or_custom_hosts(url, monkeypatch):
    monkeypatch.delenv("UNIFIERR_ALLOWED_SERVICE_HOSTS", raising=False)
    with pytest.raises(ValueError, match="UNIFIERR_ALLOWED_SERVICE_HOSTS"):
        validate_service_url(url)


def test_allows_explicitly_approved_custom_container_name(monkeypatch):
    monkeypatch.setenv("UNIFIERR_ALLOWED_SERVICE_HOSTS", "custom-radarr")
    assert validate_service_url("http://custom-radarr:7878") == "http://custom-radarr:7878"


def test_allows_tailscale_ip_over_https():
    assert validate_service_url("https://100.64.0.1:8096") == "https://100.64.0.1:8096"


@pytest.mark.parametrize("url", [
    "http://public.example.com:8096",
    "http://user:password@192.168.1.2:7878",
    "http://192.168.1.2:7878/?token=secret",
    "http://metadata.google.internal",
    "http://169.254.169.254/latest/meta-data",
    "http://[fd00:ec2::254]/latest/meta-data",
    "http://224.0.0.1",
    "https://100.100.100.200:8096",
])
def test_rejects_unsafe_service_addresses(url):
    with pytest.raises(ValueError):
        validate_service_url(url)


@pytest.mark.parametrize("url", [
    "http://127.1:8096",
    "http://2130706433:8096",
    "http://0x7f000001:8096",
    "http://0177.0.0.1:8096",
])
def test_rejects_ambiguous_numeric_hosts(url):
    with pytest.raises(ValueError, match="standard IP address"):
        validate_service_url(url)
