"""Apps installed by Unifierr get a required web login (security fix)."""
import json
from urllib.parse import parse_qs

import httpx

from app.adapters.base import Connection, ServiceKind
from app.adapters.bazarr import BazarrAdapter
from app.adapters.prowlarr import ProwlarrAdapter
from app.adapters.radarr import RadarrAdapter


async def test_arr_set_ui_login_requires_forms_auth(mock):
    host = {"id": 1, "port": 7878, "authenticationMethod": "external",
            "authenticationRequired": "disabledForLocalAddresses"}
    mock.get("http://radarr:7878/api/v3/config/host").mock(return_value=httpx.Response(200, json=host))
    put = mock.put("http://radarr:7878/api/v3/config/host/1").mock(return_value=httpx.Response(202, json=host))
    a = RadarrAdapter(Connection(kind=ServiceKind.radarr, base_url="http://radarr:7878", api_key="k"))
    await a.set_ui_login("admin", "s3cret-pass")
    sent = json.loads(put.calls.last.request.content)
    assert sent["authenticationMethod"] == "forms" and sent["authenticationRequired"] == "enabled"
    assert sent["username"] == "admin" and sent["password"] == sent["passwordConfirmation"] == "s3cret-pass"
    assert sent["port"] == 7878  # other host settings are kept
    await a.aclose()


async def test_prowlarr_uses_v1_api(mock):
    mock.get("http://prowlarr:9696/api/v1/config/host").mock(return_value=httpx.Response(200, json={"id": 1}))
    put = mock.put("http://prowlarr:9696/api/v1/config/host/1").mock(return_value=httpx.Response(202, json={}))
    a = ProwlarrAdapter(Connection(kind=ServiceKind.prowlarr, base_url="http://prowlarr:9696", api_key="k"))
    await a.set_ui_login("admin", "pw-123456")
    assert put.called
    await a.aclose()


async def test_bazarr_set_ui_login_form_fields(mock):
    post = mock.post("http://bazarr:6767/api/system/settings").mock(return_value=httpx.Response(204))
    a = BazarrAdapter(Connection(kind=ServiceKind.bazarr, base_url="http://bazarr:6767", api_key="k"))
    await a.set_ui_login("admin", "pw-123456")
    form = parse_qs(post.calls.last.request.content.decode())
    assert form["settings-auth-type"] == ["form"] and form["settings-auth-username"] == ["admin"]
    assert post.calls.last.request.headers["X-API-KEY"] == "k"
    await a.aclose()
