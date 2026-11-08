from __future__ import annotations

import os
import stat

import pytest

from app.core import config, crypto


@pytest.mark.skipif(os.name == "nt", reason="POSIX file permission bits are not available on Windows")
def test_generated_fernet_key_is_owner_only(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "config"
    data_dir.mkdir()
    monkeypatch.setenv("UNIFIERR_DATA_DIR", str(data_dir))
    monkeypatch.delenv("UNIFIERR_SECRET_KEY", raising=False)
    config.get_settings.cache_clear()
    crypto._fernet.cache_clear()

    try:
        crypto._fernet()
        key_mode = stat.S_IMODE((data_dir / "secret.key").stat().st_mode)
    finally:
        config.get_settings.cache_clear()
        crypto._fernet.cache_clear()

    assert key_mode == 0o600
