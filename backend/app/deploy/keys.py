"""Credential generation, reading, and pre-seeding for managed apps.

Allows Unifierr to configure credentials before first launch so users never have
to manually copy/paste API keys or temporary passwords. Existing configuration files
are never overwritten.
"""
from __future__ import annotations

import base64
import configparser
import contextlib
import hashlib
import os
import re
import secrets
import xml.etree.ElementTree as ET  # noqa: S405
from pathlib import Path

import yaml


def generate_api_key() -> str:
    """Generate a random 32-character hexadecimal API key."""
    return secrets.token_hex(16)


def read_arr_api_key(config_dir: str) -> str | None:
    """Read the API key from an *arr (Radarr, Sonarr, Prowlarr) config.xml file.

    Returns None if the file is missing, empty, or garbled.
    """
    path = Path(config_dir) / "config.xml"
    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            return None
        # Try XML parser first
        with contextlib.suppress(ET.ParseError):
            root = ET.fromstring(content)  # noqa: S314
            api_elem = root.find("ApiKey")
            if api_elem is not None and api_elem.text and api_elem.text.strip():
                return api_elem.text.strip()
        # Fallback regex in case of minor XML corruption
        m = re.search(r"<ApiKey>([a-fA-F0-9]{32,})</ApiKey>", content)
        if m:
            return m.group(1).strip()
    except OSError:
        return None
    return None


def read_bazarr_api_key(config_dir: str) -> str | None:
    """Read the API key from Bazarr's config file (yaml or ini).

    Returns None if missing or garbled.
    """
    cfg_dir = Path(config_dir)
    # Check YAML paths
    for rel in ("config/config.yaml", "config.yaml"):
        p = cfg_dir / rel
        if p.is_file():
            with contextlib.suppress(Exception):  # noqa: BLE001
                data = yaml.safe_load(p.read_text(encoding="utf-8", errors="replace"))
                if isinstance(data, dict):
                    auth = data.get("auth")
                    if isinstance(auth, dict):
                        key = auth.get("apikey")
                        if key and isinstance(key, str) and key.strip():
                            return key.strip()

    # Check INI paths
    for rel in ("config/config.ini", "config.ini"):
        p = cfg_dir / rel
        if p.is_file():
            with contextlib.suppress(Exception):  # noqa: BLE001
                cp = configparser.ConfigParser()
                cp.read(p, encoding="utf-8")
                if cp.has_section("auth") and cp.has_option("auth", "apikey"):
                    val = cp.get("auth", "apikey").strip()
                    if val:
                        return val
    return None


def preseed_arr_config(config_dir: str, api_key: str, port: int) -> None:
    """Write minimal config.xml for *arr applications if it does not already exist.

    Never overwrites an existing installation.
    Login is always required (Forms). Unifierr itself uses the API key, and right after the
    first start it sets a generated web login through the API (see services/installer.py),
    so nobody on the network can open the app without a password.
    """
    path = Path(config_dir) / "config.xml"
    if path.exists():
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    xml_content = (
        "<Config>\n"
        f"  <Port>{port}</Port>\n"
        f"  <ApiKey>{api_key}</ApiKey>\n"
        "  <AuthenticationMethod>Forms</AuthenticationMethod>\n"
        "  <AuthenticationRequired>Enabled</AuthenticationRequired>\n"
        "  <Branch>master</Branch>\n"
        "  <LogLevel>info</LogLevel>\n"
        "  <UrlBase></UrlBase>\n"
        "</Config>\n"
    )
    path.write_text(xml_content, encoding="utf-8")


def preseed_qbittorrent(config_dir: str, username: str, password: str) -> None:
    """Preseed qBittorrent WebUI credentials in qBittorrent.conf if absent.

    Uses PBKDF2-HMAC-SHA512 with 100,000 iterations, 16-byte salt, 64-byte key.
    Stored format: WebUI\\Password_PBKDF2="@ByteArray(<b64 salt>:<b64 hash>)"
    Also configures WebUI\\Username, WebUI\\CSRFProtection=true, and
    Downloads\\SavePath=/data/torrents/.
    Never overwrites an existing configuration file.
    """
    conf_path = Path(config_dir) / "qBittorrent" / "qBittorrent.conf"
    if conf_path.exists():
        return

    conf_path.parent.mkdir(parents=True, exist_ok=True)
    salt = os.urandom(16)
    key_hash = hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt, 100000, dklen=64)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(key_hash).decode("ascii")
    pbkdf2_val = f"@ByteArray({salt_b64}:{hash_b64})"

    conf_content = (
        "[Preferences]\n"
        f"WebUI\\Username={username}\n"
        f'WebUI\\Password_PBKDF2="{pbkdf2_val}"\n'
        "WebUI\\CSRFProtection=true\n"
        "Downloads\\SavePath=/data/torrents/\n"
    )
    conf_path.write_text(conf_content, encoding="utf-8")


def read_sabnzbd_api_key(config_dir: str) -> str | None:
    """Read SABnzbd's API key from its sabnzbd.ini ([misc] api_key).

    The linuxserver container stores it at /config/sabnzbd.ini. Returns None when missing.
    """
    for rel in ("sabnzbd.ini", "config/sabnzbd.ini"):
        path = Path(config_dir) / rel
        if not path.is_file():
            continue
        try:
            cp = configparser.ConfigParser()
            cp.read(path, encoding="utf-8", errors="replace")
            if cp.has_option("misc", "api_key"):
                key = cp.get("misc", "api_key").strip()
                if key:
                    return key
        except (OSError, configparser.Error):
            continue
        # Fallback regex in case the INI is slightly garbled
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"^\s*api_key\s*=\s*(\S+)", content, re.MULTILINE | re.IGNORECASE)
            if m:
                return m.group(1).strip()
        except OSError:
            pass
    return None


def read_nzbget_credentials(config_dir: str) -> tuple[str | None, str | None]:
    """Read NZBGet's control username/password from nzbget.conf.

    The linuxserver container stores it at /config/nzbget.conf. Returns (username, password);
    either may be None when the file is missing or the setting is absent.
    """
    path = Path(config_dir) / "nzbget.conf"
    if not path.is_file():
        return None, None
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None
    username = password = None
    m = re.search(r"^\s*ControlUsername\s*=\s*(\S+)", content, re.MULTILINE)
    if m:
        username = m.group(1).strip()
    m = re.search(r"^\s*ControlPassword\s*=\s*(\S+)", content, re.MULTILINE)
    if m:
        password = m.group(1).strip()
    return username or None, password or None


def preseed_sabnzbd(config_dir: str, api_key: str) -> None:
    """Write a minimal sabnzbd.ini with the API key if none exists.

    The host whitelist includes the container names Unifierr uses, so API calls from the
    other apps and from Unifierr itself are accepted. Never overwrites an existing file.
    """
    path = Path(config_dir) / "sabnzbd.ini"
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[misc]\n"
        f"api_key = {api_key}\n"
        "host_whitelist = unifierr, sabnzbd, localhost\n"
        "[nzb]\n"
        "dirscan_dir = /data/usenet/incoming\n"
        "complete_dir = /data/usenet/complete\n",
        encoding="utf-8",
    )


def preseed_nzbget(config_dir: str, username: str, password: str) -> None:
    """Write a minimal nzbget.conf with control credentials if none exists.

    The control user is what Unifierr and the *arr apps use to talk to NZBGet.
    Never overwrites an existing file.
    """
    path = Path(config_dir) / "nzbget.conf"
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"ControlUsername={username}\n"
        f"ControlPassword={password}\n"
        "MainDir=/config\n"
        "DestDir=/data/usenet/complete\n"
        "InterDir=/config/intermediate\n"
        "NzbDir=/config/nzb\n"
        "QueueDir=/config/queue\n"
        "TempDir=/config/tmp\n",
        encoding="utf-8",
    )
