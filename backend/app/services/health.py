"""Health overview: ping every connected app, collect their own warnings, check storage."""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.adapters.base import HealthIssue, HealthStatus, ServiceKind
from app.models import Service
from app.services.common import connection_for, get_service, get_setting, make_adapter

LOW_SPACE_BYTES = 20 * 1024**3


async def service_status(svc: Service) -> tuple[HealthStatus, list[HealthIssue]]:
    try:
        adapter = make_adapter(connection_for(svc))
    except Exception as exc:  # noqa: BLE001 - e.g. secret key changed
        return HealthStatus(ok=False, message=str(exc)), []
    try:
        status = await adapter.ping()
        issues = []
        if status.ok:
            try:
                issues = await adapter.health_issues()
            except Exception:  # noqa: BLE001 - health details are best effort
                issues = []
        return status, issues
    finally:
        await adapter.aclose()


async def all_statuses(db: AsyncSession) -> list[tuple[Service, HealthStatus, list[HealthIssue]]]:
    services = list((await db.execute(select(Service).where(Service.enabled.is_(True)))).scalars())
    results = await asyncio.gather(*(service_status(s) for s in services))
    return [(s, st, iss) for s, (st, iss) in zip(services, results, strict=True)]


async def storage_issues(db: AsyncSession) -> list[HealthIssue]:
    root = await get_setting(db, "root")
    if not root:
        return []
    try:
        from app.deploy.folders import check_folders

        report = await run_in_threadpool(check_folders, root)
    except Exception:  # noqa: BLE001
        return []
    issues = list(report.problems)
    if report.total_bytes and report.free_bytes < LOW_SPACE_BYTES:
        issues.append(HealthIssue(
            severity="warning", source="storage",
            message=f"Low disk space: {report.free_bytes // 1024**3} GB free",
            explanation="When the disk is full, downloads stop and apps can corrupt their databases.",
            fix="Delete media you no longer need or add more storage.",
        ))
    return issues


async def vpn_issues(
    db: AsyncSession,
    statuses: list[tuple[Service, HealthStatus, list[HealthIssue]]],
) -> list[HealthIssue]:
    if not await get_setting(db, "vpn_enabled"):
        return []

    qbit = await get_service(db, ServiceKind.qbittorrent)
    explanation = "The VPN option is on, but qBittorrent is not available through the Gluetun network."
    fix = (
        "Open Settings → Apps and connect or install qBittorrent through Gluetun; "
        "check the VPN container's mapped web port."
    )
    if qbit is None or not qbit.enabled:
        return [HealthIssue(
            severity="warning",
            source="gluetun",
            message="VPN routing is on, but no download client is connected",
            explanation=explanation,
            fix=fix,
        )]

    from urllib.parse import urlparse

    container_name = await get_setting(db, "vpn_container_name") or "gluetun"
    client_host = urlparse(qbit.internal_url or qbit.base_url).hostname
    client_status = next((status for service, status, _ in statuses if service.id == qbit.id), None)
    if client_host != container_name or client_status is None or not client_status.ok:
        return [HealthIssue(
            severity="warning",
            source="gluetun",
            message="qBittorrent cannot be reached through Gluetun",
            explanation=explanation,
            fix=fix,
        )]
    return []


async def overview(db: AsyncSession) -> dict:
    statuses = await all_statuses(db)
    issues: list[HealthIssue] = []
    services = []
    for svc, status, svc_issues in statuses:
        services.append({"id": svc.id, "kind": svc.kind, "name": svc.name, "status": status})
        if not status.ok:
            issues.append(HealthIssue(severity="error", source=svc.kind, message=f"{svc.name}: {status.message}",
                                      explanation=status.issues[0].explanation if status.issues else None,
                                      fix=status.issues[0].fix if status.issues else None))
        for i in svc_issues:
            issues.append(i.model_copy(update={"source": i.source or svc.kind}))
    issues.extend(await vpn_issues(db, statuses))
    issues.extend(await storage_issues(db))
    if not statuses:
        issues.append(HealthIssue(severity="warning", message="No apps connected yet",
                                  fix="Run the setup wizard from Settings."))
    overall = "error" if any(i.severity == "error" for i in issues) else (
        "warning" if any(i.severity == "warning" for i in issues) else "ok")
    return {"overall": overall, "services": services, "issues": issues}
