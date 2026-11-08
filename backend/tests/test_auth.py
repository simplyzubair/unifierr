from tests.conftest import CSRF, make_admin


async def test_health_is_public(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_first_run_bootstrap_then_locked(client):
    status = (await client.get("/api/setup/status")).json()
    assert status["has_admin"] is False and status["setup_complete"] is False
    await make_admin(client)
    assert (await client.get("/api/setup/status")).json()["has_admin"] is True
    me = await client.get("/api/auth/me")
    assert me.json()["role"] == "admin"
    # A second bootstrap must be refused.
    r = await client.post("/api/auth/bootstrap", json={"username": "evil", "password": "whatever123"}, headers=CSRF)
    assert r.status_code == 409


async def test_csrf_header_required(client):
    r = await client.post("/api/auth/bootstrap", json={"username": "admin", "password": "correct-horse-1"})
    assert r.status_code == 403


async def test_short_password_rejected(client):
    r = await client.post("/api/auth/bootstrap", json={"username": "admin", "password": "short"}, headers=CSRF)
    assert r.status_code == 400


async def test_login_logout_and_rate_limit(client):
    from app.core.security import login_ip_limiter, login_limiter

    login_limiter._fails.clear()
    login_ip_limiter._fails.clear()
    await make_admin(client)
    await client.post("/api/auth/logout", headers=CSRF)
    assert (await client.get("/api/auth/me")).status_code == 401
    bad = {"username": "admin", "password": "wrong-password"}
    for _ in range(10):
        assert (await client.post("/api/auth/login", json=bad, headers=CSRF)).status_code == 401
    assert (await client.post("/api/auth/login", json=bad, headers=CSRF)).status_code == 429
    login_limiter._fails.clear()
    ok = await client.post("/api/auth/login", json={"username": "admin", "password": "correct-horse-1"},
                           headers=CSRF)
    assert ok.status_code == 200
    cookie = ok.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


async def test_login_rate_limit_cannot_be_bypassed_with_new_usernames(client):
    from app.core.security import login_ip_limiter, login_limiter

    login_limiter._fails.clear()
    login_ip_limiter._fails.clear()
    await make_admin(client)
    for index in range(login_ip_limiter.limit):
        response = await client.post(
            "/api/auth/login",
            json={"username": f"unknown-{index}", "password": "wrong-password"},
            headers=CSRF,
        )
        assert response.status_code == 401

    response = await client.post(
        "/api/auth/login",
        json={"username": "unknown-final", "password": "wrong-password"},
        headers=CSRF,
    )
    assert response.status_code == 429
    login_limiter._fails.clear()
    login_ip_limiter._fails.clear()


def test_login_rate_limiter_bounds_tracked_keys():
    from app.core.security import LoginRateLimiter

    limiter = LoginRateLimiter(limit=2, max_keys=3)
    for index in range(10):
        limiter.fail(f"client-{index}")

    assert len(limiter._fails) == 3


def test_login_rate_limiter_expires_old_attempts(monkeypatch):
    from app.core.security import LoginRateLimiter

    moments = iter((0.0, 2.0))
    monkeypatch.setattr("app.core.security.time.monotonic", lambda: next(moments))
    limiter = LoginRateLimiter(limit=1, window=1)
    limiter.fail("client")

    limiter.check("client")

    assert "client" not in limiter._fails


async def test_user_cannot_reach_admin_routes_or_others_requests(client):
    await make_admin(client)
    r = await client.post("/api/users", json={"username": "kid", "password": "kid-password-1", "role": "user"},
                          headers=CSRF)
    assert r.status_code == 201
    await client.post("/api/auth/logout", headers=CSRF)
    await client.post("/api/auth/login", json={"username": "kid", "password": "kid-password-1"}, headers=CSRF)
    for path in ("/api/services", "/api/users", "/api/downloads", "/api/settings", "/api/system/backup"):
        assert (await client.get(path)).status_code == 403, path
    assert (await client.get("/api/requests")).json() == []


async def test_change_password_invalidates_other_sessions(client):
    await make_admin(client)
    r = await client.post("/api/auth/password",
                          json={"current_password": "correct-horse-1", "new_password": "new-password-2"},
                          headers=CSRF)
    assert r.status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 200  # this device stays signed in
    await client.post("/api/auth/logout", headers=CSRF)
    bad = await client.post("/api/auth/login", json={"username": "admin", "password": "correct-horse-1"},
                            headers=CSRF)
    assert bad.status_code == 401


async def test_security_headers(client):
    r = await client.get("/api/health")
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_every_api_route_requires_sign_in_unless_public():
    """Guard rail: a new route without current_user/require_admin fails this test."""
    from app.core.security import current_user, require_admin
    from app.main import create_app

    public = {"/api/health", "/api/setup/status", "/api/auth/bootstrap", "/api/auth/login", "/api/auth/logout",
              "/api/docs", "/api/docs/oauth2-redirect", "/api/openapi.json", "/api/{path:path}"}

    def calls(dependant):
        for sub in dependant.dependencies:
            yield sub.call
            yield from calls(sub)

    unprotected = [r.path for r in create_app().routes
                   if getattr(r, "path", "").startswith("/api/") and r.path not in public
                   and not any(c in (current_user, require_admin) for c in calls(r.dependant))]
    assert unprotected == []


async def test_concurrent_bootstrap_creates_only_one_admin(client):
    import asyncio

    bodies = [{"username": f"admin{i}", "password": "correct-horse-1"} for i in range(5)]
    results = await asyncio.gather(*(client.post("/api/auth/bootstrap", json=b, headers=CSRF) for b in bodies))
    assert sorted(r.status_code for r in results) == [200, 409, 409, 409, 409]
