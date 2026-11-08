#!/usr/bin/env bash
# ==============================================================================
# Unifierr One-Click Installer
# Installs and launches the Unifierr self-hosted media stack manager with Docker.
# ==============================================================================

set -euo pipefail

echo "=================================================="
echo "          Installing Unifierr Media Stack         "
echo "=================================================="

# 1. Verify Docker installation
if ! command -v docker >/dev/null 2>&1; then
    echo "Error: Docker is not installed." >&2
    echo "Please install Docker from https://docs.docker.com/engine/install/ before running this script." >&2
    exit 1
fi

# Verify Docker daemon is running
if ! docker info >/dev/null 2>&1; then
    echo "Error: Docker daemon is not running or current user lacks permission to access /var/run/docker.sock." >&2
    echo "Make sure the Docker service is started (e.g. 'sudo systemctl start docker') and your user is in the 'docker' group." >&2
    exit 1
fi

# 2. Verify Docker Compose (v2 or v1)
COMPOSE_CMD=""
if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
else
    echo "Error: Docker Compose is not installed." >&2
    echo "Please install Docker Compose plugin (docker compose) before running this script." >&2
    exit 1
fi

# 3. Target directory setup
INSTALL_DIR="${UNIFIERR_DIR:-$HOME/unifierr}"
echo "Setting up Unifierr directory at: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/config"
cd "$INSTALL_DIR"

# 4. Acquire docker-compose.yml
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

if [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
    echo "Using existing docker-compose.yml in $INSTALL_DIR."
elif [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
    echo "Copying local docker-compose.yml..."
    cp "$SCRIPT_DIR/docker-compose.yml" "$INSTALL_DIR/docker-compose.yml"
else
    echo "Downloading docker-compose.yml..."
    COMPOSE_URL="https://raw.githubusercontent.com/simplyzubair/unifierr/feat/unifierr-mvp/deploy/docker-compose.yml"
    curl -fsSL "$COMPOSE_URL" -o "$INSTALL_DIR/docker-compose.yml"
fi

# 5. Create default .env if missing
if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo "Configuring default environment (.env)..."
    STORAGE_ROOT="${UNIFIERR_ROOT:-/srv/unifierr}"
    case "$STORAGE_ROOT" in
        /*) ;;
        *)
            echo "Error: UNIFIERR_ROOT must be an absolute host path." >&2
            exit 1
            ;;
    esac
    case "$STORAGE_ROOT" in
        *$'\n'*|*$'\r'*)
            echo "Error: UNIFIERR_ROOT cannot contain newline characters." >&2
            exit 1
            ;;
    esac
    # Quote the Compose .env value so spaces and dollar signs remain literal.
    # Compose represents a literal apostrophe inside single quotes as \' .
    STORAGE_ROOT_ENV=${STORAGE_ROOT//\'/\\\'}
    DETECTED_UID="${SUDO_UID:-$(id -u)}"
    DETECTED_GID="${SUDO_GID:-$(id -g)}"
    if [ "$DETECTED_UID" = "0" ]; then
        DETECTED_UID="1000"
    fi
    if [ "$DETECTED_GID" = "0" ]; then
        DETECTED_GID="1000"
    fi

    DETECTED_TZ="UTC"
    if [ -f /etc/timezone ]; then
        DETECTED_TZ="$(cat /etc/timezone | tr -d ' \n\r')"
    elif [ -L /etc/localtime ]; then
        DETECTED_TZ="$(readlink /etc/localtime | sed 's|.*/zoneinfo/||')"
    fi
    DETECTED_TZ="${DETECTED_TZ:-UTC}"

    cat <<EOF > "$INSTALL_DIR/.env"
UNIFIERR_ROOT='${STORAGE_ROOT_ENV}'
UNIFIERR_BIND_ADDRESS=127.0.0.1
UNIFIERR_ALLOWED_SERVICE_HOSTS=
PUID=${DETECTED_UID}
PGID=${DETECTED_GID}
TZ=${DETECTED_TZ}
EOF
fi

# 6. Start Unifierr container
echo "Starting Unifierr with Docker Compose..."
if ! $COMPOSE_CMD pull; then
    echo "" >&2
    echo "Error: could not download the Unifierr image." >&2
    echo "Check your internet connection. If no release has been published yet, build from source:" >&2
    echo "  git clone https://github.com/simplyzubair/unifierr && cd unifierr" >&2
    echo "  docker compose --project-directory . -f deploy/docker-compose.yml -f deploy/docker-compose.build.yml up -d --build" >&2
    exit 1
fi
$COMPOSE_CMD up -d

# 7. Confirm the app is actually healthy before telling the user it's ready.
echo "Waiting for Unifierr to pass its health check..."
HEALTH_STATUS=""
for attempt in $(seq 1 45); do
    HEALTH_STATUS="$(docker inspect --format '{{.State.Health.Status}}' unifierr 2>/dev/null || true)"
    case "$HEALTH_STATUS" in
        healthy) break ;;
        unhealthy) break ;;
    esac
    sleep 2
done

if [ "$HEALTH_STATUS" != "healthy" ]; then
    echo "Error: Unifierr did not become healthy (status: ${HEALTH_STATUS:-unknown})." >&2
    echo "The container was left in place. Check it with:" >&2
    echo "  cd '$INSTALL_DIR' && $COMPOSE_CMD logs --tail 80 unifierr" >&2
    exit 1
fi

# 8. Explain the safe default bind and how to reach the interface.
echo ""
echo "=================================================="
echo "    Unifierr is healthy and ready.                 "
echo "    Web port is bound to NAS loopback (8484).      "
echo "    For other devices, use an HTTPS reverse proxy. "
echo "=================================================="
echo "Point the proxy to http://127.0.0.1:8484 on the NAS."
echo "See the Synology guide or SECURITY.md for secure access steps."
echo "To view logs:  cd $INSTALL_DIR && $COMPOSE_CMD logs -f"
echo "To stop:       cd $INSTALL_DIR && $COMPOSE_CMD down"
echo "=================================================="
