from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import (
    COOKIE_NAME,
    create_session,
    current_user,
    destroy_session,
    destroy_user_sessions,
    hash_password,
    login_limiter,
    require_admin,
    validate_new_password,
    verify_password,
)
from app.models import User
from app.services.common import get_setting

router = APIRouter()


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str = Field(min_length=1, max_length=256)


class NewUser(Credentials):
    role: str = Field(default="user", pattern="^(admin|user)$")


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class UserOut(BaseModel):
    id: int
    username: str
    role: str


def _out(u: User) -> UserOut:
    return UserOut(id=u.id, username=u.username, role=u.role)


def _set_cookie(resp: Response, token: str) -> None:
    s = get_settings()
    resp.set_cookie(COOKIE_NAME, token, max_age=s.session_hours * 3600, httponly=True, samesite="strict",
                    secure=s.secure_cookies, path="/")


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/setup/status")
async def setup_status(db: AsyncSession = Depends(get_db)) -> dict:
    from starlette.concurrency import run_in_threadpool

    from app.services.installer import docker_manager

    users = (await db.execute(select(func.count(User.id)))).scalar_one()
    try:
        docker_ok = await run_in_threadpool(docker_manager().available)
    except Exception:  # noqa: BLE001
        docker_ok = False
    return {"has_admin": users > 0, "setup_complete": bool(await get_setting(db, "setup_complete")),
            "docker_available": docker_ok, "version": __version__}


@router.post("/auth/bootstrap", response_model=UserOut)
async def bootstrap(body: Credentials, response: Response, db: AsyncSession = Depends(get_db)):
    validate_new_password(body.password)
    if (await db.execute(select(func.count(User.id)))).scalar_one() > 0:
        raise HTTPException(409, detail="An admin account already exists. Please sign in.")
    user = User(username=body.username, password_hash=hash_password(body.password), role="admin")
    db.add(user)
    await db.commit()
    _set_cookie(response, await create_session(db, user))
    return _out(user)


@router.post("/auth/login", response_model=UserOut)
async def login(body: Credentials, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    key = f"{request.client.host if request.client else '?'}:{body.username.lower()}"
    login_limiter.check(key)
    user = (await db.execute(select(User).where(User.username == body.username))).scalar_one_or_none()
    if user is None or not verify_password(user.password_hash, body.password):
        login_limiter.fail(key)
        raise HTTPException(401, detail="Wrong username or password.")
    login_limiter.reset(key)
    _set_cookie(response, await create_session(db, user))
    return _out(user)


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    await destroy_session(db, request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/auth/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return _out(user)


@router.post("/auth/password", status_code=204)
async def change_password(body: PasswordChange, request: Request, response: Response,
                          user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(400, detail="Your current password is not correct.")
    validate_new_password(body.new_password)
    user.password_hash = hash_password(body.new_password)
    await db.commit()
    # Sign out every other device, keep this one signed in with a fresh session.
    await destroy_user_sessions(db, user.id)
    _set_cookie(response, await create_session(db, user))


@router.get("/users", response_model=list[UserOut])
async def list_users(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return [_out(u) for u in (await db.execute(select(User).order_by(User.id))).scalars()]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(body: NewUser, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    validate_new_password(body.password)
    if (await db.execute(select(User).where(User.username == body.username))).scalar_one_or_none():
        raise HTTPException(409, detail="That username is taken.")
    user = User(username=body.username, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    await db.commit()
    return _out(user)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if user_id == admin.id:
        raise HTTPException(400, detail="You cannot delete your own account.")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(404, detail="User not found.")
    await db.delete(user)
    await db.commit()
