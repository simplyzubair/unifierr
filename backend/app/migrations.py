"""Run Alembic migrations programmatically (on startup and after a restore)."""
from pathlib import Path

from alembic.config import Config

from alembic import command
from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parent.parent


def sync_url() -> str:
    return get_settings().db_url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg")


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", sync_url())
    return cfg


def upgrade_db() -> None:
    command.upgrade(alembic_config(), "head")
