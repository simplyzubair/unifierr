"""Unifierr FastAPI application: REST API under /api, built frontend at /."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.api import auth, converter, media, ops, services, setup, system
from app.core.config import get_settings
from app.core.errors import UnifierrError
from app.core.logging import setup_logging
from app.core.security import CSRF_HEADER

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    from app.migrations import upgrade_db

    await run_in_threadpool(upgrade_db)
    from app.services.notify import notify_loop
    from app.services.retry_missing import retry_missing_loop
    from app.services.updater import auto_update_loop

    updates = asyncio.create_task(auto_update_loop())
    alerts = asyncio.create_task(notify_loop())
    retries = asyncio.create_task(retry_missing_loop())
    try:
        yield
    finally:
        updates.cancel()
        alerts.cancel()
        retries.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Unifierr API", version=__version__, lifespan=lifespan,
                  docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")

    @app.middleware("http")
    async def csrf_and_headers(request: Request, call_next):
        if (request.method in UNSAFE_METHODS and request.url.path.startswith("/api/")
                and request.headers.get(CSRF_HEADER) != "1"):
            return JSONResponse({"detail": "Missing security header. Please reload the page."}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if not request.url.path.startswith("/api/docs"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'",
            )
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(UnifierrError)
    async def unifierr_error(_: Request, exc: UnifierrError):
        return JSONResponse(exc.to_dict(), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", [])[1:])
        return JSONResponse({"detail": f"Invalid value for '{field}': {first.get('msg', 'invalid')}"},
                            status_code=422)

    for module in (auth, setup, services, media, ops, system, converter):
        app.include_router(module.router, prefix="/api")
    app.include_router(system.client_router, prefix="/api")

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                   include_in_schema=False)
    async def api_not_found(path: str):
        return JSONResponse({"detail": "Not found."}, status_code=404)

    static_dir: Path = settings.static_dir
    if static_dir.is_dir():
        index = static_dir / "index.html"
        root = static_dir.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            candidate = (static_dir / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(root):
                headers = {"Cache-Control": "public, max-age=31536000, immutable"} if path.startswith(
                    "assets/") else None
                return FileResponse(candidate, headers=headers)
            return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
