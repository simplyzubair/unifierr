"""Install missing apps with Docker and adopt existing ones, saving their credentials securely."""
from __future__ import annotations

import asyncio
import inspect
import logging
import re
import secrets
from functools import lru_cache
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.adapters.base import Connection, ServiceKind
from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.core.db import sessionmaker
from app.core.errors import UnifierrError
from app.models import Service
from app.services.common import get_all_settings, get_service, log_event, make_adapter, set_settings
from app.services.jobs import Job

log = logging.getLogger("unifierr.installer")

# Install order matters: download clients and indexers before the apps that use them.
INSTALL_ORDER = [ServiceKind.gluetun, ServiceKind.qbittorrent, ServiceKind.sabnzbd, ServiceKind.nzbget,
                 ServiceKind.prowlarr, ServiceKind.radarr, ServiceKind.sonarr, ServiceKind.bazarr,
                 ServiceKind.jellyfin, ServiceKind.plex]
ARR_KINDS = {ServiceKind.radarr, ServiceKind.sonarr, ServiceKind.prowlarr}
VPN_ROUTED_KINDS = {ServiceKind.qbittorrent, ServiceKind.prowlarr, ServiceKind.sabnzbd, ServiceKind.nzbget}
DISPLAY = {k: k.value.capitalize() for k in ServiceKind} | {
    ServiceKind.qbittorrent: "qBittorrent", ServiceKind.sabnzbd: "SABnzbd", ServiceKind.nzbget: "NZBGet",
}


@lru_cache
def docker_manager():
    from app.deploy.docker_manager import DockerManager

    return DockerManager(get_settings().docker_host or None)


def appdata_dir(root: str, kind: ServiceKind) -> Path:
    return Path(root) / "appdata" / kind.value


async def wait_until_up(url: str, *, max_wait: float = 180, job: Job | None = None) -> bool:
    """Poll an HTTP URL until it answers with any status below 500 (401 also means 'up')."""
    deadline = asyncio.get_running_loop().time() + max_wait
    async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
        while asyncio.get_running_loop().time() < deadline:
            try:
                r = await client.get(url)
                if r.status_code < 500:
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(3)
    if job:
        job.say(f"Gave up waiting for {url}")
    return False


async def wait_for_file_key(reader, config_dir: str, max_wait: float = 90) -> str | None:
    deadline = asyncio.get_running_loop().time() + max_wait
    while asyncio.get_running_loop().time() < deadline:
        key = await run_in_threadpool(reader, config_dir)
        if key:
            return key
        await asyncio.sleep(3)
    return None


async def save_service(db: AsyncSession, kind: ServiceKind, *, base_url: str, internal_url: str | None = None,
                       api_key: str | None = None, username: str | None = None, password: str | None = None,
                       managed: bool = False, container_name: str | None = None,
                       name: str | None = None) -> Service:
    name = name.strip() if name else None
    svc = await get_service(db, kind, name)
    if svc is None:
        svc = Service(kind=kind.value, name=name or DISPLAY[kind])
        db.add(svc)
    svc.base_url = base_url.rstrip("/")
    svc.internal_url = (internal_url or base_url).rstrip("/")
    if api_key is not None:
        svc.api_key_enc = encrypt(api_key)
    if username is not None:
        svc.username = username
    if password is not None:
        svc.password_enc = encrypt(password)
    svc.managed = managed
    svc.container_name = container_name
    svc.enabled = True
    await db.commit()
    await db.refresh(svc)
    return svc


async def secure_web_login(kind: ServiceKind, url: str, api_key: str | None, job: Job) -> tuple[str, str]:
    """Give the app's own web page a random login. Unifierr keeps using the API key."""
    username, password = "admin", secrets.token_urlsafe(16)
    adapter = make_adapter(Connection(kind=kind, base_url=url, api_key=api_key))
    try:
        await adapter.set_ui_login(username, password)
    finally:
        await adapter.aclose()
    name = DISPLAY[kind]
    job.say(f"{name} login created (see Settings → Apps → {name} → Show login).")
    return username, password


async def install_one(db: AsyncSession, job: Job, kind: ServiceKind, settings: dict) -> None:
    from app.deploy import keys
    from app.deploy.catalog import CATALOG

    name = DISPLAY[kind]
    s = job.step(f"Install {name}")
    if await get_service(db, kind):
        job.skip(s, f"{name} is already connected.")
        return
    spec = CATALOG[kind]
    root = settings["root"]

    dm = docker_manager()
    if kind == ServiceKind.gluetun:
        containers = await run_in_threadpool(dm.list_containers, False)
        existing = next((c for c in containers if "gluetun" in c.image.lower() or "gluetun" in c.name.lower()), None)
        if existing:
            settings["vpn_container_name"] = existing.name
            await run_in_threadpool(dm.connect_network, existing.name, "unifierr")
            job.skip(s, f"Using existing VPN container '{existing.name}' without changing its settings.")
            return

        vpn_env = {
            "VPN_SERVICE_PROVIDER": str(settings["vpn_provider"]),
            "VPN_TYPE": str(settings.get("vpn_type") or "openvpn"),
            "FIREWALL_INPUT_PORTS": "8080,6881,9696,8081,6789",
        }
        if settings.get("vpn_type") == "wireguard":
            vpn_env["WIREGUARD_PRIVATE_KEY"] = decrypt(settings.get("wireguard_private_key_enc")) or ""
        else:
            vpn_env["OPENVPN_USER"] = decrypt(settings.get("vpn_username_enc")) or ""
            vpn_env["OPENVPN_PASSWORD"] = decrypt(settings.get("vpn_password_enc")) or ""
        if settings.get("vpn_server_countries"):
            vpn_env["SERVER_COUNTRIES"] = str(settings["vpn_server_countries"])
        await run_in_threadpool(
            dm.install, spec, root=root, puid=int(settings["puid"]), pgid=int(settings["pgid"]),
            tz=settings["timezone"], env_overrides=vpn_env, progress=job.say,
        )
        settings["vpn_container_name"] = spec.container_name
        await set_settings(db, {"vpn_container_name": spec.container_name})
        job.ok(s, "Gluetun is running; routed apps will share its VPN network.")
        return

    cfg = appdata_dir(root, kind)
    await run_in_threadpool(cfg.mkdir, parents=True, exist_ok=True)

    api_key = username = password = None
    if kind in ARR_KINDS:
        api_key = keys.generate_api_key()
        await run_in_threadpool(keys.preseed_arr_config, str(cfg), api_key, spec.internal_port)
    elif kind == ServiceKind.qbittorrent:
        username, password = "admin", secrets.token_urlsafe(16)
        await run_in_threadpool(keys.preseed_qbittorrent, str(cfg), username, password)
    elif kind == ServiceKind.sabnzbd:
        api_key = keys.generate_api_key()
        await run_in_threadpool(keys.preseed_sabnzbd, str(cfg), api_key)
    elif kind == ServiceKind.nzbget:
        username, password = "admin", secrets.token_urlsafe(16)
        await run_in_threadpool(keys.preseed_nzbget, str(cfg), username, password)

    network_mode = None
    if settings.get("vpn_enabled") and spec.vpn_routed:
        vpn_container_name = settings.get("vpn_container_name") or "gluetun"
        network_mode = f"container:{vpn_container_name}"
    env_overrides = None
    if kind == ServiceKind.plex:
        claim = decrypt(settings.get("plex_claim_enc"))
        if claim:
            env_overrides = {"PLEX_CLAIM": claim}
    await run_in_threadpool(
        dm.install, spec, root=root, puid=int(settings["puid"]), pgid=int(settings["pgid"]),
        tz=settings["timezone"], network_mode=network_mode, env_overrides=env_overrides, progress=job.say,
    )
    url_host = settings.get("vpn_container_name", "gluetun") if network_mode else spec.container_name
    url = f"http://{url_host}:{spec.internal_port}"
    job.say(f"Waiting for {name} to start…")
    if not await wait_until_up(url + spec.healthcheck_path, job=job):
        raise UnifierrError(
            f"{name} was installed but did not start",
            explanation=f"The {name} container exists but did not answer within 3 minutes.",
            fix=f"Open Settings → Apps → {name} → Logs to see why. A slow first start can also cause this; "
                "press Retry in a minute.",
        )

    # Read the real key from the config file (the app may have kept an older one).
    if kind in ARR_KINDS:
        api_key = await wait_for_file_key(keys.read_arr_api_key, str(cfg)) or api_key
    elif kind == ServiceKind.bazarr:
        api_key = await wait_for_file_key(keys.read_bazarr_api_key, str(cfg))
        if not api_key:
            raise UnifierrError("Could not read Bazarr's API key",
                                explanation="Bazarr started but its settings file was not readable yet.",
                                fix="Press Retry in a minute.")
    elif kind == ServiceKind.sabnzbd:
        api_key = await wait_for_file_key(keys.read_sabnzbd_api_key, str(cfg)) or api_key
    elif kind == ServiceKind.nzbget:
        await wait_for_file_key(lambda d: (keys.read_nzbget_credentials(d)[1]), str(cfg))
    elif kind == ServiceKind.jellyfin:
        username = "admin"  # the Jellyfin wizard runs during the "connect everything" step

    if kind in ARR_KINDS | {ServiceKind.bazarr}:
        username, password = await secure_web_login(kind, url, api_key, job)

    await save_service(db, kind, base_url=url, internal_url=url, api_key=api_key, username=username,
                       password=password, managed=True, container_name=spec.container_name)
    job.ok(s, f"{name} is running.")
    await log_event(db, "install", f"Installed {name}.")


async def run_install(job: Job, kinds: list[ServiceKind]) -> dict:
    dm = docker_manager()
    if not await run_in_threadpool(dm.available):
        raise UnifierrError("Docker is not available", explanation=dm.error(),
                            fix="See the Unifierr install guide: the Docker socket must be mounted.")
    async with sessionmaker()() as db:
        settings = await get_all_settings(db)
        if not settings.get("root"):
            raise UnifierrError("Storage is not set up yet", fix="Finish the Storage step of the wizard first.")
        s = job.step("Prepare the private app network")
        try:
            await run_in_threadpool(dm.ensure_network, "unifierr")
            me = await run_in_threadpool(dm.self_container)
            if me is not None and "unifierr" not in me.networks:
                await run_in_threadpool(dm.connect_network, me.name, "unifierr")
            job.ok(s)
        except Exception as exc:  # noqa: BLE001
            job.fail(s, exc)
            return {"installed": []}
        requested = set(kinds)
        # Gluetun is an internal network sidecar, not a standalone user app.
        requested.discard(ServiceKind.gluetun)
        if settings.get("vpn_enabled") and requested & VPN_ROUTED_KINDS:
            requested.add(ServiceKind.gluetun)
        ordered = [k for k in INSTALL_ORDER if k in requested]
        installed = []
        vpn_ready = True
        for kind in ordered:
            if kind in VPN_ROUTED_KINDS and settings.get("vpn_enabled") and not vpn_ready:
                step = job.step(f"Install {DISPLAY[kind]}")
                job.skip(step, "Gluetun did not start, so this app was left off the VPN network.")
                continue
            try:
                await install_one(db, job, kind, settings)
                installed.append(kind.value)
            except Exception as exc:  # noqa: BLE001
                job.fail(job.steps[-1] if job.steps[-1].status == "running" else job.step(f"Install {kind}"), exc)
                await log_event(db, "install", f"Installing {DISPLAY[kind]} failed: {exc}", level="error")
                if kind == ServiceKind.gluetun:
                    vpn_ready = False
            if kind == ServiceKind.gluetun and job.steps[-1].status == "failed":
                vpn_ready = False
        if ServiceKind.plex in requested:
            # A Plex claim token is single-use and expires quickly. Do not leave it in settings
            # after the install attempt, successful or not.
            await set_settings(db, {"plex_claim_enc": None})
        return {"installed": installed}


QBIT_TEMP_PW = re.compile(r"temporary password is provided for this session:\s*(\S+)", re.IGNORECASE)


async def adopt(db: AsyncSession, kind: ServiceKind, *, base_url: str | None, api_key: str | None,
                username: str | None, password: str | None, name: str | None = None,
                internal_url: str | None = None) -> Service:
    """Connect an app that already exists. Reads credentials from its config files when possible."""
    from app.deploy import keys

    container_name = config_path = None
    if not base_url or (kind in ARR_KINDS | {ServiceKind.bazarr, ServiceKind.sabnzbd} and not api_key) \
            or (kind == ServiceKind.nzbget and not password):
        from app.deploy.detect import detect_apps

        found = [d for d in await _detect(detect_apps) if d.kind == kind]
        if found:
            d = found[0]
            container_name, config_path = d.container_name, d.config_path
            if not base_url and d.container_name:
                base_url = await _join_shared_network(d.container_name, kind) or d.reachable_url
            base_url = base_url or d.reachable_url
    if not base_url:
        raise UnifierrError(f"Could not find {DISPLAY[kind]}",
                            explanation="It was not found in Docker or on the usual network addresses.",
                            fix="Open Advanced and type its address, e.g. http://192.168.1.10:7878")
    if not api_key and config_path and kind in ARR_KINDS | {ServiceKind.bazarr, ServiceKind.sabnzbd}:
        if kind == ServiceKind.bazarr:
            reader = keys.read_bazarr_api_key
        elif kind == ServiceKind.sabnzbd:
            reader = keys.read_sabnzbd_api_key
        else:
            reader = keys.read_arr_api_key
        api_key = await run_in_threadpool(reader, config_path)
    if kind == ServiceKind.nzbget and config_path and (not username or not password):
        # linuxserver NZBGet stores its control login in nzbget.conf.
        u, p = await run_in_threadpool(keys.read_nzbget_credentials, config_path)
        username, password = username or u, password or p
    if kind == ServiceKind.qbittorrent and not password and container_name:
        # linuxserver qBittorrent >= 4.6.1 prints a temporary password in its log on every start.
        try:
            logs = await run_in_threadpool(docker_manager().logs, container_name, 500)
            matches = QBIT_TEMP_PW.findall(logs)
            if matches:  # the newest start is last in the log
                username, password = username or "admin", matches[-1]
        except Exception as exc:  # noqa: BLE001 - optional convenience only
            log.info("Could not read qBittorrent's temporary password from its log: %s", exc)

    if not api_key and kind in ARR_KINDS | {ServiceKind.bazarr, ServiceKind.sabnzbd}:
        name = DISPLAY[kind]
        where = "Settings → General → Security → API Key" if kind in ARR_KINDS | {ServiceKind.bazarr} \
            else "Settings → General → Security → API key"
        raise UnifierrError(
            f"Found {name}, but not its API key",
            explanation=f"Unifierr reads the key from {name}'s settings folder. That only works when {name} "
                        "runs in Docker on this machine. Here it runs somewhere else, so the folder is not visible.",
            fix=f"Click Advanced and paste the key from {name} → {where}.",
        )
    if kind == ServiceKind.nzbget and not password:
        raise UnifierrError(
            "Found NZBGet, but not its control login",
            explanation="Unifierr reads the control username and password from NZBGet's settings folder. That "
                        "only works when NZBGet runs in Docker on this machine.",
            fix="Click Advanced and type NZBGet's control username and password.",
        )
    conn = Connection(kind=kind, base_url=base_url.rstrip("/"), api_key=api_key, username=username,
                      password=password)
    adapter = make_adapter(conn)
    try:
        status = await adapter.ping()
    finally:
        await adapter.aclose()
    # Jellyfin without key is fine (wizard/login happens during wiring); everything else must answer OK.
    if not status.ok and not (kind == ServiceKind.jellyfin and not api_key):
        raise UnifierrError(f"Could not connect to {DISPLAY[kind]}: {status.message}",
                            explanation=status.issues[0].explanation if status.issues else None,
                            fix=status.issues[0].fix if status.issues else
                            "Check the address and credentials under Advanced.")
    svc = await save_service(db, kind, base_url=base_url, internal_url=internal_url, api_key=api_key,
                             username=username, password=password, managed=False, container_name=container_name,
                             name=name)
    await log_event(db, "setup", f"Connected existing {svc.name} at {base_url}.")
    return svc


async def _join_shared_network(container_name: str, kind: ServiceKind) -> str | None:
    """Attach an existing container to the shared 'unifierr' network so the other apps can reach it
    by name. Non-destructive: the container keeps running and all its settings stay the same."""
    from app.deploy.catalog import CATALOG

    dm = docker_manager()
    try:
        await run_in_threadpool(dm.ensure_network, "unifierr")
        me = await run_in_threadpool(dm.self_container)
        if me is not None and "unifierr" not in me.networks:
            await run_in_threadpool(dm.connect_network, me.name, "unifierr")
        await run_in_threadpool(dm.connect_network, container_name, "unifierr")
    except Exception as exc:  # noqa: BLE001 - fall back to the detected address
        log.info("Could not add %s to the unifierr network: %s", container_name, exc)
        return None
    url = f"http://{container_name}:{CATALOG[kind].internal_port}"
    return url if await wait_until_up(url + CATALOG[kind].healthcheck_path, max_wait=10) else None


async def _detect(detect_apps):
    """detect_apps may be sync (blocking) or async; run it without blocking the event loop."""
    if inspect.iscoroutinefunction(detect_apps):
        return await detect_apps(docker_manager())
    return await run_in_threadpool(detect_apps, docker_manager())
