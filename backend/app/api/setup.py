import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.adapters.base import ServiceKind
from app.core.db import get_db
from app.core.security import require_admin
from app.models import User
from app.services import installer, wiring
from app.services.common import get_setting, log_event, set_settings
from app.services.jobs import Job, jobs
from app.services.services_out import service_out

router = APIRouter(dependencies=[Depends(require_admin)])


class FoldersIn(BaseModel):
    root: str = Field(min_length=2, max_length=255)
    puid: int = Field(default=1000, ge=0, le=65535)
    pgid: int = Field(default=1000, ge=0, le=65535)
    timezone: str = Field(default="UTC", max_length=64, pattern=r"^[A-Za-z0-9_+\-/]+$")


class InstallIn(BaseModel):
    kinds: list[ServiceKind] = Field(min_length=1)


class AdoptIn(BaseModel):
    kind: ServiceKind
    base_url: str | None = Field(default=None, max_length=255, pattern=r"^https?://[^\s]+$")
    api_key: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=256)


@router.get("/setup/environment")
async def environment():
    from app.deploy.environment import detect_environment

    return await run_in_threadpool(detect_environment, installer.docker_manager())


@router.get("/setup/detect")
async def detect():
    from app.deploy.detect import detect_apps

    return await installer._detect(detect_apps)


@router.post("/setup/folders")
async def folders(body: FoldersIn, db: AsyncSession = Depends(get_db)):
    from pathlib import PurePosixPath

    from app.deploy.folders import prepare_folders

    root = body.root.rstrip("/") or "/"
    if not PurePosixPath(root).is_absolute() or ".." in PurePosixPath(root).parts:
        raise HTTPException(400, detail="Use a full folder path such as /srv/unifierr.")
    if root in ("/", "/etc", "/usr", "/bin", "/proc", "/sys", "/dev", "/boot", "/var", "/root"):
        raise HTTPException(400, detail="That is a system folder. Choose a folder just for your media.")
    shared = os.environ.get("UNIFIERR_ROOT", "").rstrip("/")
    if shared and not (root == shared or root.startswith(shared + "/")):
        raise HTTPException(400, detail=f"The storage folder must be {shared} or a folder inside it. "
                                        "That is the folder shared with Unifierr in docker-compose.yml "
                                        "(UNIFIERR_ROOT). To use another disk, change UNIFIERR_ROOT and "
                                        "restart Unifierr.")
    report = await run_in_threadpool(prepare_folders, root, body.puid, body.pgid)
    await set_settings(db, {"root": root, "puid": body.puid, "pgid": body.pgid, "timezone": body.timezone})
    await log_event(db, "setup", f"Storage prepared at {root}.")
    return report


@router.post("/setup/install")
async def install(body: InstallIn):
    kinds = list(dict.fromkeys(body.kinds))

    async def run(job: Job):
        return await installer.run_install(job, kinds)

    return {"job_id": jobs.start("install", run).id}


@router.post("/setup/adopt")
async def adopt(body: AdoptIn, db: AsyncSession = Depends(get_db)):
    svc = await installer.adopt(db, body.kind, base_url=body.base_url, api_key=body.api_key,
                                username=body.username, password=body.password)
    return await service_out(svc)


@router.post("/setup/wire")
async def wire():
    return {"job_id": jobs.start("wire", wiring.run_wiring).id}


@router.post("/setup/complete")
async def complete(db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    await set_settings(db, {"setup_complete": True})
    await log_event(db, "setup", f"Setup finished by {user.username}.")
    return {"setup_complete": await get_setting(db, "setup_complete")}


@router.get("/jobs/{job_id}")
async def job_status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, detail="Job not found. It may have finished long ago or Unifierr restarted.")
    return job
