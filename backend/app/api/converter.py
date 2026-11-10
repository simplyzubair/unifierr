"""The one endpoint Unmanic's safety check may call: "is this movie being watched right now?".

Unmanic has no login, so it never gets the Jellyfin key. It gets a random token that can only ask this question.
"""
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import ServiceKind
from app.core.db import get_db
from app.services.common import adapter_for, get_setting, set_settings

router = APIRouter()
TOKEN_SETTING = "converter_token"  # noqa: S105 - name of the setting, not a secret


async def converter_token(db: AsyncSession) -> str:
    token = await get_setting(db, TOKEN_SETTING)
    if not token:
        token = secrets.token_urlsafe(32)
        await set_settings(db, {TOKEN_SETTING: token})
    return token


@router.get("/converter/playing")
async def playing(name: str = Query(min_length=1, max_length=512),
                  x_unifierr_token: str = Header(default=""), db: AsyncSession = Depends(get_db)) -> dict:
    expected = await get_setting(db, TOKEN_SETTING)
    if not expected or not secrets.compare_digest(x_unifierr_token, expected):
        raise HTTPException(401, detail="Wrong converter token.")
    async with adapter_for(db, ServiceKind.jellyfin, required=False) as jellyfin:
        if jellyfin is None:
            return {"playing": False}
        return {"playing": name in await jellyfin.playing_file_names()}
