"""Self-update: detect a newer image, start the helper, and never loop on an image that already failed."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import updater
from tests.conftest import CSRF, make_admin


def fake_manager(ref="ghcr.io/me/unifierr:latest", running_id="sha256:aaa", newest_id="sha256:bbb", pull_error=None):
    me = SimpleNamespace(id="c1", name="unifierr")
    container = MagicMock()
    container.attrs = {"Config": {"Image": ref}, "Image": running_id}
    running = SimpleNamespace(id=running_id, labels={"org.opencontainers.image.revision": "old1"},
                              attrs={"Created": "2026-11-01"})
    client = MagicMock()
    client.containers.get.return_value = container
    client.images.get.return_value = running
    if pull_error:
        client.images.pull.side_effect = pull_error
    else:
        client.images.pull.return_value = SimpleNamespace(
            id=newest_id, labels={"org.opencontainers.image.revision": "new2"}, attrs={"Created": "2026-11-09"})
    return SimpleNamespace(available=lambda: True, self_container=lambda: me, client=client)


def test_locally_built_image_is_not_updatable():
    info, target = updater.check_now(fake_manager(ref="unifierr:local"), pull=True)
    assert info["supported"] is False and "built on this computer" in info["reason"] and target is None


def test_digest_pinned_image_is_not_updatable():
    info, _ = updater.check_now(fake_manager(ref="ghcr.io/me/unifierr@sha256:abc"), pull=True)
    assert info["supported"] is False


def test_newer_image_is_reported_and_same_image_is_not():
    info, target = updater.check_now(fake_manager(), pull=True)
    assert info["available"] is True and target == "sha256:bbb"
    assert info["current"]["revision"] == "old1" and info["latest"]["revision"] == "new2"
    info, _ = updater.check_now(fake_manager(newest_id="sha256:aaa"), pull=True)
    assert info["available"] is False


def test_running_image_record_gone_still_works():
    """Docker's containerd image store drops the record of an image whose tag moved on, while it still runs."""
    dm = fake_manager()
    dm.client.images.get.side_effect = LookupError("No such image")
    info, target = updater.check_now(dm, pull=True)
    assert info["supported"] and info["current"] == {"id": "aaa", "revision": None, "created": None}
    assert info["available"] is True and target == "sha256:bbb"


def test_check_without_pull_never_contacts_the_registry():
    dm = fake_manager()
    info, _ = updater.check_now(dm, pull=False)
    assert "available" not in info
    dm.client.images.pull.assert_not_called()


def test_registry_failure_is_reported_without_leaking_the_token(monkeypatch):
    monkeypatch.setenv("UNIFIERR_REGISTRY_TOKEN", "ghp_secret123")
    info, target = updater.check_now(fake_manager(pull_error=RuntimeError("denied: token=ghp_secret123")), pull=True)
    assert "Could not download" in info["error"] and "ghp_secret123" not in info["error"] and target is None


def test_helper_runs_from_new_image_with_the_servers_volumes():
    dm = fake_manager()
    updater.start_helper(dm, "unifierr", "sha256:bbb")
    args, kwargs = dm.client.containers.run.call_args
    assert args == ("sha256:bbb",)
    assert kwargs["command"] == ["unifierr", "sha256:bbb"] and kwargs["volumes_from"] == ["unifierr"]
    assert kwargs["entrypoint"] == ["python", "-m", "app.deploy.selfupdate"]
    assert kwargs["auto_remove"] is True and kwargs["network_mode"] == "none"


@pytest.fixture
def ticks(monkeypatch, client):
    started = []
    monkeypatch.setattr(updater, "docker_manager", lambda: fake_manager())
    monkeypatch.setattr(updater, "start_helper", lambda dm, name, target: started.append(target))
    return started


async def _turn_on_auto_update():
    from app.core.db import sessionmaker
    from app.services.common import set_settings

    async with sessionmaker()() as db:
        await set_settings(db, {"auto_update": True})


async def test_auto_update_does_nothing_when_switched_off(ticks):
    await updater._auto_tick()
    assert ticks == []


async def test_auto_update_starts_when_on_and_newer(ticks):
    await _turn_on_auto_update()
    await updater._auto_tick()
    assert ticks == ["sha256:bbb"]


async def test_auto_update_waits_while_a_setup_job_runs(ticks, monkeypatch):
    await _turn_on_auto_update()
    monkeypatch.setattr(updater.jobs, "any_running", lambda: True)
    await updater._auto_tick()
    assert ticks == []


async def test_auto_update_does_not_retry_an_image_that_already_failed(ticks, tmp_path):
    from app.core.config import get_settings

    await _turn_on_auto_update()
    (get_settings().data_dir / "update-result.json").write_text(
        json.dumps({"ok": False, "to": "sha256:bbb", "message": "unhealthy"}), encoding="utf-8")
    await updater._auto_tick()
    assert ticks == []


async def test_update_api_is_admin_only_and_toggle_persists(client, monkeypatch):
    monkeypatch.setattr(updater, "docker_manager", lambda: fake_manager(ref="unifierr:local"))
    assert (await client.get("/api/system/update")).status_code == 401
    await make_admin(client)
    status = (await client.get("/api/system/update")).json()
    assert status["supported"] is False and status["auto_update"] is False and status["version"]
    r = await client.put("/api/system/update/settings", json={"auto_update": True}, headers=CSRF)
    assert r.json()["auto_update"] is True
    assert (await client.get("/api/system/update")).json()["auto_update"] is True
    r = await client.post("/api/system/update/apply", headers=CSRF)
    assert r.status_code == 409 and "built on this computer" in r.json()["explanation"]


def _stateful_manager():
    """Docker that remembers a started helper, like the real thing."""
    dm = fake_manager()
    helper = SimpleNamespace(status="running", remove=MagicMock())
    started = {"on": False}
    me = dm.client.containers.get.return_value

    def get(name):
        if name.endswith("-updater"):
            if started["on"]:
                return helper
            raise LookupError(name)
        return me

    dm.client.containers.get.side_effect = get
    dm.client.containers.run.side_effect = lambda *a, **k: started.update(on=True)
    return dm, helper


def test_running_helper_is_never_removed_and_blocks_a_second_update():
    dm, helper = _stateful_manager()
    updater.start_helper(dm, "unifierr", "sha256:bbb")
    with pytest.raises(updater.UnifierrError) as err:
        updater.start_helper(dm, "unifierr", "sha256:bbb")
    assert err.value.status_code == 409 and "already in progress" in err.value.message
    helper.remove.assert_not_called()
    assert dm.client.containers.run.call_count == 1


def test_finished_leftover_helper_is_replaced():
    dm, helper = _stateful_manager()
    updater.start_helper(dm, "unifierr", "sha256:bbb")
    helper.status = "exited"
    updater.start_helper(dm, "unifierr", "sha256:bbb")
    helper.remove.assert_called_once_with(force=True)
    assert dm.client.containers.run.call_count == 2


async def test_two_simultaneous_applies_start_exactly_one_swap(client, monkeypatch):
    import asyncio

    await make_admin(client)
    dm, _ = _stateful_manager()
    monkeypatch.setattr(updater, "docker_manager", lambda: dm)
    from app.core.db import sessionmaker

    async with sessionmaker()() as db:
        results = await asyncio.gather(updater.apply(db, "a"), updater.apply(db, "b"), return_exceptions=True)
    assert dm.client.containers.run.call_count == 1
    assert sum(isinstance(r, dict) and r["started"] for r in results) == 1
    assert any(isinstance(r, updater.UnifierrError) for r in results)  # the other was refused, not duplicated
