import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.crypto import decrypt, encrypt
from app.core.db import get_db
from app.core.errors import UnifierrError
from app.core.logging import redact
from app.core.security import require_admin
from app.models import Service
from app.services.common import log_event
from app.services.installer import docker_manager
from app.services.jobs import Job, jobs
from app.services.services_out import ServiceOut, service_out

router = APIRouter(dependencies=[Depends(require_admin)])


class ServicePatch(BaseModel):
    base_url: str | None = Field(default=None, max_length=255, pattern=r"^https?://[^\s]+$")
    api_key: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=256)
    enabled: bool | None = None


async def _get(db: AsyncSession, service_id: int) -> Service:
    svc = await db.get(Service, service_id)
    if svc is None:
        raise HTTPException(404, detail="App not found.")
    return svc


def _require_container(svc: Service) -> str:
    if not svc.container_name:
        raise UnifierrError(f"{svc.name} is not a Docker container Unifierr knows about",
                            explanation="Unifierr can only restart, update or read logs of apps running in Docker.",
                            fix=f"Manage {svc.name} where it was installed.")
    return svc.container_name


def _require_managed(svc: Service, action: str) -> None:
    if not svc.managed:
        raise UnifierrError(f"{svc.name} was not installed by Unifierr",
                            explanation=f"To avoid breaking your existing setup, Unifierr can only {action} "
                                        "apps it installed itself.",
                            fix=f"Manage {svc.name} the way you installed it (e.g. your NAS app store).")


@router.get("/services", response_model=list[ServiceOut])
async def list_services(db: AsyncSession = Depends(get_db)):
    rows = list((await db.execute(select(Service).order_by(Service.id))).scalars())
    return await asyncio.gather(*(service_out(s) for s in rows))


@router.post("/services/{service_id}/test", response_model=ServiceOut)
async def test_service(service_id: int, db: AsyncSession = Depends(get_db)):
    return await service_out(await _get(db, service_id))


@router.patch("/services/{service_id}", response_model=ServiceOut)
async def patch_service(service_id: int, body: ServicePatch, db: AsyncSession = Depends(get_db)):
    svc = await _get(db, service_id)
    data = body.model_dump(exclude_unset=True)
    if "base_url" in data and data["base_url"]:
        svc.base_url = data["base_url"].rstrip("/")
        if not svc.managed:
            svc.internal_url = svc.base_url
    if "api_key" in data:
        svc.api_key_enc = encrypt(data["api_key"])
    if "username" in data:
        svc.username = data["username"] or None
    if "password" in data:
        svc.password_enc = encrypt(data["password"])
    if "enabled" in data and data["enabled"] is not None:
        svc.enabled = data["enabled"]
    await db.commit()
    await log_event(db, "settings", f"Updated connection settings for {svc.name}.")
    return await service_out(svc)


@router.get("/services/{service_id}/credentials")
async def service_credentials(service_id: int, db: AsyncSession = Depends(get_db)):
    """Show the login Unifierr created for an app (e.g. Jellyfin, qBittorrent) so the user can sign in to it."""
    svc = await _get(db, service_id)
    await log_event(db, "security", f"Login details for {svc.name} were viewed.", level="warning")
    return {"username": svc.username, "password": decrypt(svc.password_enc)}


@router.delete("/services/{service_id}", status_code=204)
async def forget_service(service_id: int, db: AsyncSession = Depends(get_db)):
    """Forget the connection only. Never deletes containers, settings or media."""
    svc = await _get(db, service_id)
    await db.delete(svc)
    await db.commit()
    await log_event(db, "settings", f"Unifierr forgot {svc.name}. Nothing was deleted from the app itself.")


@router.post("/services/{service_id}/restart", status_code=202)
async def restart_service(service_id: int, db: AsyncSession = Depends(get_db)):
    svc = await _get(db, service_id)
    _require_managed(svc, "restart")
    await run_in_threadpool(docker_manager().restart, _require_container(svc))
    await log_event(db, "services", f"Restarted {svc.name}.")
    return {"ok": True}


@router.post("/services/{service_id}/update")
async def update_service(service_id: int, db: AsyncSession = Depends(get_db)):
    svc = await _get(db, service_id)
    name = _require_container(svc)
    _require_managed(svc, "update")
    display = svc.name

    async def run(job: Job):
        s = job.step(f"Update {display}")
        info = await run_in_threadpool(docker_manager().update, name, job.say)
        job.ok(s, f"{display} now runs {info.image}.")
        return {"image": info.image}

    return {"job_id": jobs.start("update", run).id}


@router.get("/services/{service_id}/logs")
async def service_logs(service_id: int, tail: int = Query(200, ge=10, le=2000), db: AsyncSession = Depends(get_db)):
    svc = await _get(db, service_id)
    text = await run_in_threadpool(docker_manager().logs, _require_container(svc), tail)
    return {"logs": redact(text)}
