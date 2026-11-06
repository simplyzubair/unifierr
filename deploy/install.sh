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
    COMPOSE_URL="https://raw.githubusercontent.com/simplyzubair/unifierr/main/deploy/docker-compose.yml"
    curl -fsSL "$COMPOSE_URL" -o "$INSTALL_DIR/docker-compose.yml"
fi

# 5. Create default .env if missing
if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo "Configuring default environment (.env)..."
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
UNIFIERR_ROOT=/srv/unifierr
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
    echo "  docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.build.yml up -d --build" >&2
    exit 1
fi
$COMPOSE_CMD up -d

# 7. Print completion message and URL
HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")"
echo ""
echo "=================================================="
echo "    Unifierr is running! Access the web UI at:    "
echo "        http://${HOST_IP:-localhost}:8484         "
echo "=================================================="
echo "To view logs:  cd $INSTALL_DIR && $COMPOSE_CMD logs -f"
echo "To stop:       cd $INSTALL_DIR && $COMPOSE_CMD down"
echo "=================================================="
