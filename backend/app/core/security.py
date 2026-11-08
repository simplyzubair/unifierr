"""Local authentication: argon2 password hashes + server-side sessions in an httpOnly cookie.

CSRF: every state-changing request (POST/PUT/PATCH/DELETE) must carry the header
`X-Unifierr-CSRF: 1`. Browsers cannot add custom headers on cross-site requests without
a CORS preflight, and Unifierr sends no CORS headers, so forged requests are rejected.
Cookies are also SameSite=Strict.
"""
import hashlib
import secrets
import time
from collections import OrderedDict
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.models import Session, User

COOKIE_NAME = "unifierr_session"
CSRF_HEADER = "x-unifierr-csrf"
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def validate_new_password(password: str) -> None:
    if len(password) < 12:
        raise HTTPException(400, detail="Password must be at least 12 characters.")
    if len(password) > 256:
        raise HTTPException(400, detail="Password is too long.")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(db: AsyncSession, user: User) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(hours=get_settings().session_hours)
    db.add(Session(token_hash=_token_hash(token), user_id=user.id, expires_at=expires))
    await db.commit()
    return token


async def destroy_session(db: AsyncSession, token: str | None) -> None:
    if token:
        await db.execute(delete(Session).where(Session.token_hash == _token_hash(token)))
        await db.commit()


async def destroy_user_sessions(db: AsyncSession, user_id: int) -> None:
    await db.execute(delete(Session).where(Session.user_id == user_id))
    await db.commit()


async def current_user_optional(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    row = (await db.execute(select(Session).where(Session.token_hash == _token_hash(token)))).scalar_one_or_none()
    if row is None:
        return None
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expires < datetime.now(UTC):
        await db.delete(row)
        await db.commit()
        return None
    return await db.get(User, row.user_id)


async def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise HTTPException(401, detail="Please sign in.")
    return user


async def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, detail="Only an administrator can do this.")
    return user


class LoginRateLimiter:
    """Limit failed attempts per key with a bounded in-memory tracking table."""

    def __init__(self, limit: int = 10, window: int = 300, max_keys: int = 4096):
        self.limit, self.window = limit, window
        self.max_keys = max(1, max_keys)
        self._fails: OrderedDict[str, list[float]] = OrderedDict()
        self._last_prune = 0.0

    def _prune_expired(self, now: float) -> None:
        if now - self._last_prune < self.window:
            return
        cutoff = now - self.window
        for key, timestamps in list(self._fails.items()):
            recent = [stamp for stamp in timestamps if stamp > cutoff]
            if recent:
                self._fails[key] = recent
            else:
                del self._fails[key]
        self._last_prune = now

    def check(self, key: str) -> None:
        now = time.monotonic()
        self._prune_expired(now)
        recent = [stamp for stamp in self._fails.get(key, []) if now - stamp < self.window]
        if recent:
            self._fails[key] = recent
            self._fails.move_to_end(key)
        else:
            self._fails.pop(key, None)
        if len(recent) >= self.limit:
            raise HTTPException(429, detail="Too many failed sign-in attempts. Wait a few minutes.")

    def fail(self, key: str) -> None:
        now = time.monotonic()
        self._prune_expired(now)
        if key not in self._fails and len(self._fails) >= self.max_keys:
            self._fails.popitem(last=False)
        self._fails.setdefault(key, []).append(now)
        self._fails.move_to_end(key)

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)


# Per-account lockout prevents password guessing across different source IPs.
login_limiter = LoginRateLimiter(limit=10)
# A looser source limit slows username spraying without quickly locking out
# everyone who shares a household network or reverse proxy.
login_ip_limiter = LoginRateLimiter(limit=100)
