#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d "${TMPDIR:-/tmp}/unifierr-install-test.XXXXXX")"
trap 'rm -rf -- "$test_root"' EXIT

mkdir -p "$test_root/bin" "$test_root/home"
cat > "$test_root/bin/docker" <<'MOCK_DOCKER'
#!/usr/bin/env bash
case "$1:${2:-}" in
    info:*) exit 0 ;;
    compose:version|compose:pull|compose:up) exit 0 ;;
    inspect:*) printf '%s\n' "${MOCK_HEALTH_STATUS:-healthy}" ;;
    *) exit 1 ;;
esac
MOCK_DOCKER
chmod +x "$test_root/bin/docker"
cat > "$test_root/bin/hostname" <<'MOCK_HOSTNAME'
#!/usr/bin/env bash
exit 1
MOCK_HOSTNAME
chmod +x "$test_root/bin/hostname"

run_installer() {
    local install_dir="$1"
    local storage_root="$2"
    local health_status="${3:-healthy}"
    env \
        "PATH=$test_root/bin:$PATH" \
        "HOME=$test_root/home" \
        "UNIFIERR_DIR=$install_dir" \
        "UNIFIERR_ROOT=$storage_root" \
        "MOCK_HEALTH_STATUS=$health_status" \
        bash "$repo_root/deploy/install.sh" >"$test_root/installer.log" 2>&1
}

valid_install="$test_root/valid"
storage_root="$test_root/media library"
run_installer "$valid_install" "$storage_root"
grep -Fqx "UNIFIERR_ROOT='$storage_root'" "$valid_install/.env"
grep -Fqx "UNIFIERR_BIND_ADDRESS=127.0.0.1" "$valid_install/.env"
grep -Fqx "UNIFIERR_ALLOWED_SERVICE_HOSTS=" "$valid_install/.env"
grep -Fq "Web port is bound to NAS loopback (8484)." "$test_root/installer.log"
grep -Fq "Point the proxy to http://127.0.0.1:8484 on the NAS." "$test_root/installer.log"
if grep -Fq "http://<NAS-or-server-IP>:8484" "$test_root/installer.log"; then
    echo "Installer printed a LAN URL while using the loopback-only default." >&2
    exit 1
fi

quoted_install="$test_root/quoted"
quoted_storage_root="$test_root/media it's"
run_installer "$quoted_install" "$quoted_storage_root"
escaped_storage_root=${quoted_storage_root//\'/\\\'}
grep -Fqx "UNIFIERR_ROOT='$escaped_storage_root'" "$quoted_install/.env"

invalid_install="$test_root/invalid"
if run_installer "$invalid_install" relative/path; then
    echo "Installer accepted a relative UNIFIERR_ROOT." >&2
    exit 1
fi
grep -Fq "UNIFIERR_ROOT must be an absolute host path" "$test_root/installer.log"

unhealthy_install="$test_root/unhealthy"
if run_installer "$unhealthy_install" "$storage_root" unhealthy; then
    echo "Installer reported success before the container was healthy." >&2
    exit 1
fi
grep -Fq "did not become healthy (status: unhealthy)" "$test_root/installer.log"
grep -Fq "docker compose logs --tail 80 unifierr" "$test_root/installer.log"

echo "Installer storage-path checks passed."
