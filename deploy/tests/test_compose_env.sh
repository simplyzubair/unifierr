#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d "${TMPDIR:-/tmp}/unifierr-compose-env-test.XXXXXX")"
PYTHON="${PYTHON:-python3}"
trap 'rm -rf -- "$test_root"' EXIT

storage_root="/tmp/unifierr media it's"
escaped_storage_root=${storage_root//\'/\\\'}
cat >"$test_root/.env" <<EOF
UNIFIERR_ROOT='$escaped_storage_root'
UNIFIERR_DOCKER_HOST=tcp://docker-socket-proxy:2375
PUID=1000
PGID=1000
TZ=UTC
EOF

docker compose \
    --env-file "$test_root/.env" \
    -f "$repo_root/deploy/docker-compose.yml" \
    config --format json |
    "$PYTHON" -c '
import json
import sys

expected = "/tmp/unifierr media it\047s"
config = json.load(sys.stdin)
service = config["services"]["unifierr"]
assert service["environment"]["UNIFIERR_ROOT"] == expected
assert service["environment"]["UNIFIERR_DOCKER_HOST"] == "tcp://docker-socket-proxy:2375"
assert any(
    volume.get("source") == expected and volume.get("target") == expected
    for volume in service["volumes"]
), "UNIFIERR_ROOT bind mount did not preserve the configured path"
'

echo "Compose storage-path parsing checks passed."
