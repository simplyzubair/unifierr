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
from app.models import Service
from app.services.common import (
    DOWNLOAD_CLIENTS,
    MOVIES_PATH,
    TORRENTS_MOVIES,
    TORRENTS_TV,
    TV_PATH,
    USENET_MOVIES,
    USENET_TV,
    adapter_for,
    get_service,
    get_setting,
    internal_host_port,
    log_event,
    set_settings,
)
from app.services.jobs import Job

ARR_CATEGORIES = {ServiceKind.radarr: ("radarr", TORRENTS_MOVIES), ServiceKind.sonarr: ("tv-sonarr", TORRENTS_TV)}
USENET_SAVE_PATHS = {ServiceKind.radarr: USENET_MOVIES, ServiceKind.sonarr: USENET_TV}
DEFAULT_PORTS = {
    ServiceKind.radarr: 7878, ServiceKind.sonarr: 8989, ServiceKind.prowlarr: 9696,
    ServiceKind.qbittorrent: 8080, ServiceKind.sabnzbd: 8080, ServiceKind.nzbget: 6789,
    ServiceKind.bazarr: 6767, ServiceKind.jellyfin: 8096, ServiceKind.plex: 32400,
}
CLIENT_DISPLAY = {ServiceKind.qbittorrent: "qBittorrent", ServiceKind.sabnzbd: "SABnzbd",
                  ServiceKind.nzbget: "NZBGet"}


def _internal_url(svc) -> str:
    return (svc.internal_url or svc.base_url).rstrip("/")


async def _selected_download_client(db: AsyncSession) -> tuple[ServiceKind | None, Service | None]:
    """The download client the user picked in the wizard, falling back to whichever is connected."""
    choice = await get_setting(db, "download_client")
    if choice:
        try:
            chosen = ServiceKind(str(choice))
        except ValueError:
            chosen = None
        if chosen is not None:
            svc = await get_service(db, chosen)
            if svc is not None:
                return chosen, svc
    for kind in DOWNLOAD_CLIENTS:
        svc = await get_service(db, kind)
        if svc is not None:
            return kind, svc
    return None, None


async def _wire_arr_basics(db: AsyncSession, job: Job) -> None:
    dl_kind, dl_svc = await _selected_download_client(db)
    dl_name = CLIENT_DISPLAY.get(dl_kind, "a download client") if dl_kind else None
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

        s = job.step(f"Connect {name} to {dl_name or 'a download client'}")
        if dl_svc is None or dl_kind is None:
            job.skip(s, "No download client (qBittorrent, SABnzbd or NZBGet) is connected.")
            continue
        category, torrent_path = ARR_CATEGORIES[kind]
        try:
            host, port, ssl = internal_host_port(dl_svc, DEFAULT_PORTS[dl_kind])
            if dl_kind == ServiceKind.qbittorrent:
                async with adapter_for(db, ServiceKind.qbittorrent) as q:
                    await q.ensure_category(category, torrent_path)
                async with adapter_for(db, kind) as arr:
                    await arr.ensure_qbittorrent_client(
                        host=host, port=port, username=dl_svc.username or "",
                        password=decrypt(dl_svc.password_enc) or "", category=category, use_ssl=ssl,
                    )
            else:
                # Usenet: the same categories, but downloads land in /data/usenet/…
                save_path = USENET_SAVE_PATHS[kind]
                async with adapter_for(db, dl_kind) as dl:
                    await dl.ensure_category(category, save_path)
                async with adapter_for(db, kind) as arr:
                    await arr.ensure_usenet_client(
                        client=dl_kind.value, host=host, port=port,
                        api_key=decrypt(dl_svc.api_key_enc) if dl_svc.api_key_enc else None,
                        username=dl_svc.username, password=decrypt(dl_svc.password_enc) or None,
                        category=category, use_ssl=ssl,
                    )
            job.ok(s, f"Downloads for {name} go through {dl_name} to {torrent_path if dl_kind == ServiceKind.qbittorrent else save_path}")
        except Exception as exc:  # noqa: BLE001
            job.fail(s, exc)


async def _wire_prowlarr(db: AsyncSession, job: Job) -> None:
    prowlarr = await get_service(db, ServiceKind.prowlarr)
    app_ids: dict[ServiceKind, int] = {}
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
                app = await p.ensure_application(
                    kind=kind.value, app_url=_internal_url(svc), app_api_key=decrypt(svc.api_key_enc) or "",
                    prowlarr_url=_internal_url(prowlarr),
                )
                if isinstance(app, dict) and app.get("id") is not None:
                    app_ids[kind] = int(app["id"])
            job.ok(s, f"Indexers you add in Unifierr are copied to {name} automatically.")
        except Exception as exc:  # noqa: BLE001
            job.fail(s, exc)

    # Verify the Prowlarr -> *arr sync actually carries Usenet indexers over.
    s = job.step("Copy Usenet indexers to Radarr and Sonarr")
    if prowlarr is None:
        job.skip(s, "Prowlarr is not connected.")
        return
    if not app_ids:
        job.skip(s, "Radarr and Sonarr are not connected, so there is nowhere to copy indexers yet.")
        return
    try:
        async with adapter_for(db, ServiceKind.prowlarr) as p:
            usenet = [i for i in await p.indexers() if str(i.protocol).lower() == "usenet" and i.enabled]
            if not usenet:
                job.skip(s, "No Usenet indexers are set up yet. Add one under Indexers and it is copied over.")
                return
            for app_id in app_ids.values():
                await p.sync_application(app_id)
        job.ok(s, f"{len(usenet)} Usenet indexer(s) pushed to Radarr and Sonarr.")
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


async def run_wiring(job: Job) -> dict:
    async with sessionmaker()() as db:
        await _wire_arr_basics(db, job)
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
