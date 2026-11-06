# Architecture

```
Browser ──► Unifierr container (port 8484)
            ├── FastAPI  /api/*          backend/app/api        (routes, auth, validation)
            │     └── services/          orchestration: wiring, installer, media/requests, health, jobs
            │           ├── adapters/    one HTTP client per app (Radarr, Sonarr, Prowlarr, qBittorrent,
            │           │                Bazarr, Jellyfin, Plex) → normalized models (adapters/base.py)
            │           └── deploy/      Docker (docker-py), environment + app detection, folders, key files
            ├── SQLite   /config/unifierr.db   (SQLAlchemy 2 async + Alembic migrations)
            └── Static SPA  /            frontend/ (Vite + React + TypeScript + Tailwind)

Docker network "unifierr": radarr:7878  sonarr:8989  prowlarr:9696  qbittorrent:8080  bazarr:6767  jellyfin:8096
Shared storage (same path inside every container): UNIFIERR_ROOT/data → /data
```

**Key decisions**
- **One container.** FastAPI serves the API and the pre-built SPA. No Node.js at runtime, and a smaller attack surface.
  We chose Vite/React over Next.js because the UI is a private, signed-in app, so server-side rendering adds nothing.
- **SQLite.** One household, low write rate, and backup is a single file. `UNIFIERR_DATABASE_URL` allows Postgres later.
- **Drive proven engines through their APIs.** Unifierr never edits another app's database.
  The only files it writes are *first-start* config files (API key, login) for apps it installs itself, and never over an existing file.
- **Same-path mount.** `UNIFIERR_ROOT` is mounted at the same path in Unifierr as on the host,
  so paths Unifierr creates are valid for the containers it starts, and it can read adopted apps' `config.xml` to get their API keys.
- **Idempotent wiring.** Every "ensure_*" call checks what already exists first, so "Connect everything" can be pressed many times.
- **Long tasks are jobs.** Install, wiring and updates run in the background and report steps (ok / skipped / failed with explanation + fix) that the UI polls.

**Adding a new app** (e.g. SABnzbd): add a `ServiceKind`, an adapter, a `CATALOG` entry, an image matcher in
`deploy/detect.py`, and a wiring step in `services/wiring.py`.
