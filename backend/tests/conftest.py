import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

CSRF = {"X-Unifierr-CSRF": "1"}


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Every test gets its own data dir, database and secret key."""
    from app.core import config, crypto

    monkeypatch.setenv("UNIFIERR_DATA_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("UNIFIERR_DOCKER_HOST", "")
    monkeypatch.delenv("UNIFIERR_SECRET_KEY", raising=False)
    monkeypatch.setenv("UNIFIERR_STATIC_DIR", str(tmp_path / "nostatic"))
    config.get_settings.cache_clear()
    crypto._fernet.cache_clear()
    yield
    config.get_settings.cache_clear()
    crypto._fernet.cache_clear()


@pytest_asyncio.fixture
async def client():
    from app.core.db import reset_engine
    from app.main import create_app
    from app.migrations import upgrade_db
    from app.services.installer import docker_manager

    docker_manager.cache_clear()
    await reset_engine()
    upgrade_db()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await reset_engine()


async def make_admin(client: AsyncClient, username: str = "admin", password: str = "correct-horse-1"):  # noqa: S107
    r = await client.post("/api/auth/bootstrap", json={"username": username, "password": password}, headers=CSRF)
    assert r.status_code == 200, r.text
    return r.json()
