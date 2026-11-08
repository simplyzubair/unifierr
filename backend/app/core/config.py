"""Runtime settings. Everything comes from environment variables (prefix UNIFIERR_)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UNIFIERR_", env_file=".env", extra="ignore")

    # Where Unifierr keeps its own database, secret key and backups.
    data_dir: Path = Path("/config")
    # Optional explicit database URL. Defaults to SQLite inside data_dir.
    database_url: str | None = None
    # Port the web UI listens on (used for docs/links only; uvicorn decides the real one).
    port: int = 8484
    # Session lifetime in hours.
    session_hours: int = 24 * 14
    # Set true when served over HTTPS (reverse proxy) so cookies get the Secure flag.
    secure_cookies: bool = False
    # Path to the built frontend. If it exists, FastAPI serves it.
    static_dir: Path = Path(__file__).resolve().parent.parent / "static"
    # Docker socket. Empty string disables Docker features.
    docker_host: str = "unix:///var/run/docker.sock"
    log_level: str = "INFO"
    # Self-update: how often to look for a newer image (seconds) when auto-update is on.
    update_check_seconds: int = 900
    # Optional login for a private registry (e.g. GHCR with a read:packages token). Public images need none.
    registry_user: str | None = None
    registry_token: str | None = None
    # Where people get the desktop/Android apps; shown on the Updates page.
    download_url: str = "https://unifierr.skillsgeek.com"

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite+aiosqlite:///{(self.data_dir / 'unifierr.db').as_posix()}"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
