"""Database tables. Change these only together with a new Alembic migration."""
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")  # admin | user
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Session(Base):
    __tablename__ = "sessions"
    # sha256 of the random cookie value; the raw token is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Service(Base):
    """One connected external app (Radarr, Sonarr, Prowlarr, qBittorrent, Bazarr, Jellyfin, Plex)."""

    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint("kind", "name", name="uq_service_kind_name"),
        CheckConstraint("length(trim(name)) > 0", name="ck_service_name_nonempty"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(64))
    base_url: Mapped[str] = mapped_column(String(255))  # how Unifierr reaches it
    internal_url: Mapped[str | None] = mapped_column(String(255), nullable=True)  # how other apps reach it
    api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    managed: Mapped[bool] = mapped_column(Boolean, default=False)  # installed by Unifierr
    container_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class MediaRequest(Base):
    __tablename__ = "media_requests"
    __table_args__ = (UniqueConstraint("service_id", "media_type", "tmdb_id", "tvdb_id", name="uq_request_media"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Keep the label after a service is forgotten, and for requests created before multi-instance support.
    service_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    media_type: Mapped[str] = mapped_column(String(16))  # movie | series
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tvdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    poster_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # pending | approved | denied | failed. "downloading"/"available" are computed live.
    status: Mapped[str] = mapped_column(String(16), default="pending")
    external_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Radarr movie id / Sonarr series id
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Event(Base):
    """Activity / troubleshooting log shown in the UI."""

    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    level: Mapped[str] = mapped_column(String(8), default="info")  # info | warning | error
    source: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[Any] = mapped_column(JSON, nullable=True)
