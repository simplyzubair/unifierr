from pydantic import BaseModel

from app.adapters.base import HealthStatus
from app.models import Service
from app.services.health import service_status


class ServiceOut(BaseModel):
    id: int
    kind: str
    name: str
    base_url: str
    managed: bool
    container_name: str | None
    enabled: bool
    has_api_key: bool
    has_login: bool
    status: HealthStatus | None = None


async def service_out(svc: Service, *, with_status: bool = True) -> ServiceOut:
    status = (await service_status(svc))[0] if with_status and svc.enabled else None
    return ServiceOut(id=svc.id, kind=svc.kind, name=svc.name, base_url=svc.base_url, managed=svc.managed,
                      container_name=svc.container_name, enabled=svc.enabled,
                      has_api_key=svc.api_key_enc is not None,
                      has_login=bool(svc.username and svc.password_enc), status=status)
