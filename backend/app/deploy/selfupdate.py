"""Throw-away helper that swaps Unifierr's own container for the newer image.

A container cannot replace itself (stopping it would stop the code doing the replacing), so
services/updater.py starts this module in a short-lived second container built from the NEW image. It shares
the server's volumes (Docker socket and /config), recreates the server container with the same settings,
waits until it is healthy, and writes the outcome to /config/update-result.json for the UI.
Run as: python -m app.deploy.selfupdate <container name> <target image id>
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from app.core.config import get_settings
from app.core.errors import UnifierrError
from app.deploy.docker_manager import DockerManager

RESULT_FILE = "update-result.json"


def run(name: str, target: str | None = None, manager: DockerManager | None = None) -> bool:
    manager = manager or DockerManager(get_settings().docker_host or None)
    old_image = None
    try:
        old_image = manager.client.containers.get(name).image.id
        # Pulling was already done by the server; this only recreates (and checks) the container.
        manager.update(name, print, pull=False, require_managed=False, healthy_timeout=150)
        ok, message = True, "Updated and healthy."
    except UnifierrError as exc:
        ok, message = False, f"{exc.message}. {exc.explanation or ''}".strip()
    except Exception as exc:  # noqa: BLE001 - record any failure for the UI
        ok, message = False, f"Update failed: {exc}"
    result = {"ok": ok, "message": message, "from": old_image, "to": target,
              "at": datetime.now(UTC).isoformat()}
    try:
        (get_settings().data_dir / RESULT_FILE).write_text(json.dumps(result), encoding="utf-8")
    except OSError as exc:
        print(f"Could not write {RESULT_FILE}: {exc}", file=sys.stderr)
    print(message)
    return ok


if __name__ == "__main__":
    sys.exit(0 if len(sys.argv) == 3 and run(sys.argv[1], sys.argv[2]) else 1)
