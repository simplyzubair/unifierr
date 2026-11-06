# syntax=docker/dockerfile:1

# -----------------------------------------------------------------------------
# Stage 1: Build Frontend SPA
# -----------------------------------------------------------------------------
FROM node:22-alpine AS frontend-builder
WORKDIR /build

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2: Runtime Image (Python 3.12)
# -----------------------------------------------------------------------------
FROM python:3.12-slim

# Note on non-root execution:
# Docker socket access (/var/run/docker.sock) requires root privileges or membership
# in the docker group, whose GID varies across host distributions (Synology, Unraid,
# TrueNAS, Ubuntu, etc.). To provide an out-of-the-box working experience for beginners
# without host-specific GID mapping, the container runs as root.
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UNIFIERR_DATA_DIR=/config \
    UNIFIERR_DOCKER_HOST=unix:///var/run/docker.sock

# Install backend dependencies and package (production only, no dev extras)
COPY backend/pyproject.toml /app/
COPY backend/alembic.ini /app/
COPY backend/alembic /app/alembic
COPY backend/app /app/app

RUN pip install --no-cache-dir .

# Copy built frontend into the app's static directory
COPY --from=frontend-builder /build/dist /app/app/static

# Copy entrypoint script
COPY deploy/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create config volume mount point
RUN mkdir -p /config

EXPOSE 8484

# Health check using standard Python urllib (no external dependencies needed)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8484/api/health", timeout=3)' || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
