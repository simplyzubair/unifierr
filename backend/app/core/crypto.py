"""Encryption for stored credentials (API keys, passwords).

A random Fernet key is generated on first start and stored in <data_dir>/secret.key
with owner-only permissions. Set UNIFIERR_SECRET_KEY to supply your own instead.
"""
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    env_key = os.environ.get("UNIFIERR_SECRET_KEY")
    if env_key:
        return Fernet(env_key.encode())
    path = get_settings().data_dir / "secret.key"
    if not path.exists():
        key = Fernet.generate_key()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
    return Fernet(path.read_bytes().strip())


def encrypt(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:  # wrong/rotated key
        raise RuntimeError(
            "Stored credentials cannot be decrypted. The secret.key file changed or is missing."
        ) from exc
