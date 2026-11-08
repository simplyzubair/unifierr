"""Auto-integration: connect all apps to each other (docs/CONTRACTS.md section 4).

Every step is idempotent and reports ok / skipped / failed with an explanation, so the
wizard's "Connect everything" button can be pressed again safely.
"""
from __future__ import annotations

import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import ServiceKind
from app.core.crypto import decrypt, encrypt
from app.core.db import sessionmaker
from app.core.errors import UnifierrError
from app.services.common import (
    MOVIES_PATH,
    TORRENTS_MOVIES,
    TORRENTS_TV,
    TV_PATH,
    adapter_for,
    get_service,
    get_setting,
    internal_host_port,
    log_event,
    set_settings,
)
from app.services.jobs import Job

ARR_CATEGORIES = {ServiceKind.radarr: ("radarr", TORRENTS_MOVIES), ServiceKind.sonarr: ("tv-sonarr", TORRENTS_TV)}
DEFAULT_PORTS = {
    ServiceKind.radarr: 7878, ServiceKind.sonarr: 8989, ServiceKind.prowlarr: 9696,
    ServiceKind.qbittorrent: 8080, ServiceKind.bazarr: 6767, ServiceKind.jellyfin: 8096, ServiceKind.plex: 32400,
}


def _internal_url(svc) -> str:
    return (svc.internal_url or svc.base_url).rstrip("/")


async def _wire_arr_basics(db: AsyncSession, job: Job) -> None:
    qbit = await get_service(db, ServiceKind.qbittorrent)
    for kind, root in ((ServiceKind.radarr, MOVIES_PATH), (ServiceKind.sonarr, TV_PATH)):
        name = kind.value.capitalize()
        svc = await get_service(db, kind)
        s = job.step(f"Set {name} media folder")
        if svc is None:
            job.skip(s, f"{name} is not connected.")
            continue
        try:
            async with adapter_for(db, kind) as arr:
                existing = [f.get("path") for f in await arr.root_folders() if f.get("path")]
                if not svc.managed and existing and root not in existing:
                    # Never change an existing setup: keep the folders the user already has.
                    job.skip(s, f"Kept your existing {name} media folder: {existing[0]}")
                    continue
                await arr.ensure_root_folder(root)
            job.ok(s, f"{name} saves to {root}")
        except Exception as exc:  # noqa: BLE001
            job.fail(s, exc)

        s = job.step(f"Connect {name} to qBittorrent")
        if qbit is None:
            job.skip(s, "qBittorrent is not connected.")
            continue
        category, save_path = ARR_CATEGORIES[kind]
        try:
            host, port, _ = internal_host_port(qbit, DEFAULT_PORTS[ServiceKind.qbittorrent])
            async with adapter_for(db, ServiceKind.qbittorrent) as q:
                await q.ensure_category(category, save_path)
            async with adapter_for(db, kind) as arr:
                await arr.ensure_qbittorrent_client(
                    host=host, port=port, username=qbit.username or "",
                    password=decrypt(qbit.password_enc) or "", category=category,
                )
            job.ok(s, f"Downloads for {name} go to {save_path}")
        except Exception as exc:  # noqa: BLE001
            job.fail(s, exc)


async def _wire_prowlarr(db: AsyncSession, job: Job) -> None:
    prowlarr = await get_service(db, ServiceKind.prowlarr)
    for kind in (ServiceKind.radarr, ServiceKind.sonarr):
        name = kind.value.capitalize()
        s = job.step(f"Share indexers with {name}")
        svc = await get_service(db, kind)
        if prowlarr is None:
            job.skip(s, "Prowlarr is not connected.")
            continue
        if svc is None:
            job.skip(s, f"{name} is not connected.")
            continue
        try:
            async with adapter_for(db, ServiceKind.prowlarr) as p:
                await p.ensure_application(
                    kind=kind.value, app_url=_internal_url(svc), app_api_key=decrypt(svc.api_key_enc) or "",
                    prowlarr_url=_internal_url(prowlarr),
                )
            job.ok(s, f"Indexers you add in Unifierr are copied to {name} automatically.")
        except Exception as exc:  # noqa: BLE001
            job.fail(s, exc)


async def _wire_bazarr(db: AsyncSession, job: Job) -> None:
    bazarr = await get_service(db, ServiceKind.bazarr)
    for kind in (ServiceKind.radarr, ServiceKind.sonarr):
        name = kind.value.capitalize()
        s = job.step(f"Connect subtitles (Bazarr) to {name}")
        svc = await get_service(db, kind)
        if bazarr is None:
            job.skip(s, "Bazarr is not connected.")
            continue
        if svc is None:
            job.skip(s, f"{name} is not connected.")
            continue
        try:
            host, port, _ = internal_host_port(svc, DEFAULT_PORTS[kind])
            async with adapter_for(db, ServiceKind.bazarr) as b:
                await b.ensure_arr_connection(kind=kind.value, host=host, port=port,
                                              api_key=decrypt(svc.api_key_enc) or "")
            job.ok(s)
        except Exception as exc:  # noqa: BLE001
            job.fail(s, exc)
    if bazarr is not None:
        s = job.step("Choose subtitle language")
        try:
            lang = await get_setting(db, "language") or "en"
            async with adapter_for(db, ServiceKind.bazarr) as b:
                await b.ensure_default_language_profile([lang])
            job.ok(s, f"Subtitles will be fetched in '{lang}'.")
        except Exception as exc:  # noqa: BLE001
            job.fail(s, exc)


async def _wire_jellyfin(db: AsyncSession, job: Job) -> bool:
    svc = await get_service(db, ServiceKind.jellyfin)
    if svc is None:
        return False
    s = job.step("Prepare Jellyfin")
    try:
        async with adapter_for(db, ServiceKind.jellyfin) as jf:
            if svc.api_key_enc is None:
                if await jf.startup_needed():
                    username = svc.username or "admin"
                    password = secrets.token_urlsafe(12)
                    await jf.run_startup_wizard(username, password)
                    svc.username, svc.password_enc = username, encrypt(password)
                    await db.commit()
                    job.say("Created the Jellyfin admin account (see Settings → Apps → Jellyfin → Show login).")
                elif not (svc.username and svc.password_enc):
                    raise _needs_jellyfin_login()
                token = await jf.authenticate(svc.username or "admin", decrypt(svc.password_enc) or "")
                jf.conn.api_key = token
                api_key = await jf.create_api_key("Unifierr")
                svc.api_key_enc = encrypt(api_key)
                await db.commit()
        job.ok(s, "Jellyfin is ready.")
    except Exception as exc:  # noqa: BLE001
        job.fail(s, exc)
        return True

    s = job.step("Create Jellyfin libraries")
    try:
        async with adapter_for(db, ServiceKind.jellyfin) as jf:
            await jf.ensure_library("Movies", "movies", MOVIES_PATH)
            await jf.ensure_library("Shows", "tvshows", TV_PATH)
        job.ok(s, "Movies and Shows libraries exist.")
    except Exception as exc:  # noqa: BLE001
        job.fail(s, exc)
    return True


def _needs_jellyfin_login():
    return UnifierrError(
        "Jellyfin needs a login",
        explanation="This Jellyfin was set up before, so Unifierr needs an admin username and password "
                    "(or an API key) to connect.",
        fix="In Settings → Apps → Jellyfin → Advanced, enter the Jellyfin admin login or an API key, then retry.",
    )


async def _wire_plex(db: AsyncSession, job: Job) -> bool:
    svc = await get_service(db, ServiceKind.plex)
    if svc is None:
        return False
    s = job.step("Create Plex libraries")
    try:
        async with adapter_for(db, ServiceKind.plex) as plex:
            await plex.ensure_library("Movies", "movies", MOVIES_PATH)
            await plex.ensure_library("TV Shows", "tvshows", TV_PATH)
        job.ok(s, "Movies and TV Shows libraries exist.")
    except Exception as exc:  # noqa: BLE001
        job.fail(s, exc)
    return True


async def _wire_notifications(db: AsyncSession, job: Job) -> None:
    for server_kind in (ServiceKind.jellyfin, ServiceKind.plex):
        server = await get_service(db, server_kind)
        if server is None or server.api_key_enc is None:
            continue
        host, port, ssl = internal_host_port(server, DEFAULT_PORTS[server_kind])
        for kind in (ServiceKind.radarr, ServiceKind.sonarr):
            name = kind.value.capitalize()
            s = job.step(f"Tell {server_kind.value.capitalize()} about new {name} downloads")
            if await get_service(db, kind) is None:
                job.skip(s, f"{name} is not connected.")
                continue
            try:
                async with adapter_for(db, kind) as arr:
                    await arr.ensure_media_server_notification(
                        kind=server_kind.value, host=host, port=port,
                        api_key=decrypt(server.api_key_enc) or "", use_ssl=ssl)
                job.ok(s, "New movies and episodes appear in your library right after they finish.")
            except Exception as exc:  # noqa: BLE001
                job.fail(s, exc)


async def _wire_trash_profiles(db: AsyncSession, job: Job) -> None:
    profile_choice = await get_setting(db, "trash_profile")
    if not profile_choice:
        return
    from app.services.trash import sync_app_trash

    for kind in (ServiceKind.radarr, ServiceKind.sonarr):
        await sync_app_trash(db, job, kind, str(profile_choice))


async def run_wiring(job: Job) -> dict:
    async with sessionmaker()() as db:
        await _wire_arr_basics(db, job)
        await _wire_trash_profiles(db, job)
        await _wire_prowlarr(db, job)
        await _wire_bazarr(db, job)
        has_jf = await _wire_jellyfin(db, job)
        has_plex = await _wire_plex(db, job)
        if not (has_jf or has_plex):
            s = job.step("Media server")
            job.skip(s, "No Jellyfin or Plex connected. You can add one later.")
        await _wire_notifications(db, job)
        failed = [s.name for s in job.steps if s.status == "failed"]
        if has_jf or has_plex:
            await set_settings(db, {"media_server": "jellyfin" if has_jf else "plex"})
        message = (f"Connecting apps finished with problems: {', '.join(failed)}" if failed
                   else "Connected all apps.")
        await log_event(db, "wiring", message, level="error" if failed else "info")
        return {"failed": failed}
