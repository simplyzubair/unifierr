"""Prowlarr v1 adapter (API v1): indexers and syncing them to Radarr/Sonarr."""
from __future__ import annotations

from typing import Any, ClassVar

from app.adapters._arr_common import ArrBase, parse_json
from app.adapters.base import Indexer, IndexerSchema, ServiceKind
from app.core.errors import NotFound, ServiceUnavailable

_SKIP_FIELDS = {"definitionFile", "baseUrl"}


def _indexer(d: dict[str, Any], status: str | None = None) -> Indexer:
    return Indexer(
        id=int(d["id"]),
        name=str(d.get("name") or d.get("definitionName") or "Indexer"),
        protocol=str(d.get("protocol") or "torrent"),
        enabled=bool(d.get("enable", False)),
        privacy=d.get("privacy"),
        implementation=d.get("implementation"),
        status=status,
    )


class ProwlarrAdapter(ArrBase):
    kind: ClassVar[ServiceKind] = ServiceKind.prowlarr
    display_name: ClassVar[str] = "Prowlarr"
    default_port: ClassVar[int] = 9696
    api_prefix: ClassVar[str] = "/api/v1"
    app_label: ClassVar[str] = "prowlarr"

    async def _statuses(self) -> dict[int, str]:
        """indexerId -> human text for indexers that Prowlarr has temporarily disabled."""
        try:
            data = await self._json("GET", "/indexerstatus")
        except ServiceUnavailable:
            return {}
        out: dict[int, str] = {}
        for s in data or []:
            till = s.get("disabledTill")
            if till and "indexerId" in s:
                out[int(s["indexerId"])] = f"disabled until {str(till)[:16].replace('T', ' ')} (too many failures)"
        return out

    async def indexers(self) -> list[Indexer]:
        data = await self._json("GET", "/indexer")
        statuses = await self._statuses()
        return [_indexer(d, statuses.get(int(d["id"]), "ok" if d.get("enable") else "disabled")) for d in data or []]

    async def indexer_schemas(self) -> list[IndexerSchema]:
        data = await self._json("GET", "/indexer/schema")
        out: list[IndexerSchema] = []
        for d in data or []:
            required = [
                    {
                        "name": f.get("name"),
                        "label": f.get("label"),
                        "type": f.get("type"),
                        "value": f.get("value"),
                        "helpText": f.get("helpText"),
                        "selectOptions": [
                            {"value": option.get("value"), "name": option.get("name")}
                            for option in f.get("selectOptions", [])
                            if isinstance(option, dict)
                        ],
                    }
                    for f in d.get("fields", [])
                    if not f.get("advanced") and f.get("type") not in ("info", "hidden")
                and f.get("name") not in _SKIP_FIELDS
                and not str(f.get("name", "")).startswith(("baseSettings.", "torrentBaseSettings."))
            ]
            out.append(IndexerSchema(
                name=str(d.get("definitionName") or d.get("name") or ""),
                implementation=str(d.get("implementation") or ""),
                protocol=str(d.get("protocol") or "torrent"),
                privacy=d.get("privacy"),
                description=d.get("description"),
                language=d.get("language"),
                required_fields=required,
            ))
        return out

    async def add_indexer(self, definition_name: str, fields: dict[str, Any] | None = None) -> Indexer:
        wanted = definition_name.strip().lower()
        for ex in await self._json("GET", "/indexer") or []:
            if wanted in (str(ex.get("definitionName", "")).lower(), str(ex.get("name", "")).lower()):
                return _indexer(ex, "ok" if ex.get("enable") else "disabled")  # already added
        schemas = await self._json("GET", "/indexer/schema")
        schema = next((s for s in schemas or []
                       if wanted in (str(s.get("definitionName", "")).lower(), str(s.get("name", "")).lower())), None)
        if schema is None:
            raise NotFound(f"Prowlarr has no indexer called '{definition_name}'",
                           explanation="The name does not match any indexer in Prowlarr's catalogue.",
                           fix="Pick an indexer from the list instead of typing its name.")
        body = {k: v for k, v in schema.items() if k != "id"}
        body["enable"] = True
        body.setdefault("tags", [])
        # Prowlarr supplies valid base URLs for definitions with dynamic URL choices.
        # Use its first choice when the schema has no default so the user need not
        # discover or type an internal provider setting by hand.
        indexer_urls = schema.get("indexerUrls")
        if isinstance(indexer_urls, list) and indexer_urls:
            for field in body.get("fields", []):
                if (
                    field.get("name") == "baseUrl"
                    and field.get("selectOptionsProviderAction")
                    and not field.get("value")
                    and isinstance(indexer_urls[0], str)
                ):
                    field["value"] = indexer_urls[0]
                    break
        if not body.get("appProfileId"):
            profiles = await self._json("GET", "/appprofile")
            body["appProfileId"] = int(profiles[0]["id"]) if profiles else 1
        if fields:
            body["fields"] = [{**f, "value": fields[f["name"]]} if f.get("name") in fields else f
                              for f in body.get("fields", [])]
        resp = await self._api("POST", "/indexer", params={"forceSave": "true"}, json=body)
        return _indexer(parse_json(resp, self.display_name), "ok")

    async def delete_indexer(self, indexer_id: int) -> None:
        await self._api("DELETE", f"/indexer/{indexer_id}")

    async def set_indexer_enabled(self, indexer_id: int, enabled: bool) -> Indexer:
        current = await self._json("GET", f"/indexer/{indexer_id}")
        current["enable"] = enabled
        resp = await self._api("PUT", f"/indexer/{indexer_id}", params={"forceSave": "true"}, json=current)
        return _indexer(parse_json(resp, self.display_name), "ok" if enabled else "disabled")

    async def test_all_indexers(self) -> list[dict[str, Any]]:
        resp = await self._api("POST", "/indexer/testall", timeout=120.0)
        out: list[dict[str, Any]] = []
        for r in parse_json(resp, self.display_name) or []:
            errors = [str(e.get("errorMessage") or e) if isinstance(e, dict) else str(e)
                      for e in r.get("validationFailures") or r.get("errors") or []]
            out.append({"id": r.get("id"), "isValid": bool(r.get("isValid")), "errors": errors})
        return out

    async def ensure_application(self, *, kind: str, app_url: str, app_api_key: str,
                                 prowlarr_url: str, app_name: str | None = None) -> dict[str, Any]:
        kind = str(kind).lower()
        if kind not in ("radarr", "sonarr"):
            raise ServiceUnavailable(f"Unsupported application: {kind}")
        return await self._ensure_provider(
            "applications", implementation=kind.capitalize(), match_field="baseUrl", match_value=app_url,
            values={"prowlarrUrl": prowlarr_url, "baseUrl": app_url, "apiKey": app_api_key},
            top={"name": app_name or kind.capitalize(), "syncLevel": "fullSync", "tags": []},
        )

    async def sync_application(self, app_id: int) -> None:
        """Ask Prowlarr to push its indexers (torrent AND Usenet) to Radarr/Sonarr right now."""
        await self._api("POST", f"/application/{app_id}/sync")
