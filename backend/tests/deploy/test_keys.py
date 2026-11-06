from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

from app.deploy.keys import (
    generate_api_key,
    preseed_arr_config,
    preseed_qbittorrent,
    read_arr_api_key,
    read_bazarr_api_key,
)


def test_generate_api_key() -> None:
    key1 = generate_api_key()
    key2 = generate_api_key()
    assert len(key1) == 32
    assert len(key2) == 32
    assert re.fullmatch(r"[0-9a-f]{32}", key1)
    assert key1 != key2


def test_arr_config_preseed_and_read(tmp_path: Path) -> None:
    cfg_dir = str(tmp_path)
    api_key = generate_api_key()

    # Read before preseed -> None
    assert read_arr_api_key(cfg_dir) is None

    # Preseed
    preseed_arr_config(cfg_dir, api_key, 7878)
    config_file = tmp_path / "config.xml"
    assert config_file.is_file()

    # Content checks: Forms login always required, port
    content = config_file.read_text(encoding="utf-8")
    assert f"<ApiKey>{api_key}</ApiKey>" in content
    assert "<Port>7878</Port>" in content
    assert "<AuthenticationMethod>Forms</AuthenticationMethod>" in content
    assert "<AuthenticationRequired>Enabled</AuthenticationRequired>" in content

    # Read back
    assert read_arr_api_key(cfg_dir) == api_key

    # No-overwrite test: calling preseed again with a different key must NOT change the file
    other_key = generate_api_key()
    preseed_arr_config(cfg_dir, other_key, 8989)
    assert read_arr_api_key(cfg_dir) == api_key
    assert other_key not in config_file.read_text(encoding="utf-8")


def test_read_arr_api_key_handles_corrupt_files(tmp_path: Path) -> None:
    cfg_dir = str(tmp_path)
    config_file = tmp_path / "config.xml"

    # Empty file
    config_file.write_text("", encoding="utf-8")
    assert read_arr_api_key(cfg_dir) is None

    # Malformed XML but has regex match
    config_file.write_text("<Config><ApiKey>0123456789abcdef0123456789abcdef</ApiKey>", encoding="utf-8")
    assert read_arr_api_key(cfg_dir) == "0123456789abcdef0123456789abcdef"

    # Completely broken non-xml
    config_file.write_text("random binary junk without any key", encoding="utf-8")
    assert read_arr_api_key(cfg_dir) is None


def test_read_bazarr_api_key_yaml_and_ini(tmp_path: Path) -> None:
    cfg_dir = str(tmp_path)

    # Missing file
    assert read_bazarr_api_key(cfg_dir) is None

    # YAML format in config/config.yaml
    yaml_file = tmp_path / "config" / "config.yaml"
    yaml_file.parent.mkdir(parents=True, exist_ok=True)
    yaml_file.write_text("auth:\n  apikey: bazarr_secret_yaml_key\n", encoding="utf-8")
    assert read_bazarr_api_key(cfg_dir) == "bazarr_secret_yaml_key"

    # Remove yaml and test INI format in config.ini
    yaml_file.unlink()
    ini_file = tmp_path / "config" / "config.ini"
    ini_file.write_text("[auth]\napikey = bazarr_secret_ini_key\n", encoding="utf-8")
    assert read_bazarr_api_key(cfg_dir) == "bazarr_secret_ini_key"

    # Corrupt INI file returns None
    ini_file.write_text("invalid [auth section missing header", encoding="utf-8")
    assert read_bazarr_api_key(cfg_dir) is None


def test_preseed_qbittorrent_and_verify_pbkdf2(tmp_path: Path) -> None:
    cfg_dir = str(tmp_path)
    username = "admin"
    password = "MySuperSecretPassword123!"

    # Preseed
    preseed_qbittorrent(cfg_dir, username, password)

    conf_file = tmp_path / "qBittorrent" / "qBittorrent.conf"
    assert conf_file.is_file()

    content = conf_file.read_text(encoding="utf-8")
    assert f"WebUI\\Username={username}" in content
    assert "WebUI\\CSRFProtection=true" in content
    assert "Downloads\\SavePath=/data/torrents/" in content

    # Extract PBKDF2 string
    m = re.search(r'WebUI\\Password_PBKDF2="@ByteArray\(([^:]+):([^)]+)\)"', content)
    assert m is not None, f"Failed to match PBKDF2 string in: {content}"

    salt_b64, hash_b64 = m.group(1), m.group(2)
    salt = base64.b64decode(salt_b64)
    expected_hash = base64.b64decode(hash_b64)

    # Recompute PBKDF2 and verify match
    recomputed_hash = hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt, 100000, dklen=64)
    assert recomputed_hash == expected_hash

    # Test no-overwrite behavior
    preseed_qbittorrent(cfg_dir, "otheruser", "DifferentPassword")
    content_after = conf_file.read_text(encoding="utf-8")
    assert f"WebUI\\Username={username}" in content_after
    assert "otheruser" not in content_after
