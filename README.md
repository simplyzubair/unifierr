<img src="assets/icon.svg" width="64" height="64" alt="">

# Unifierr

**One app to install, connect and run your whole self-hosted media setup.**

Unifierr sets up Radarr, Sonarr, Prowlarr, qBittorrent, Bazarr and Jellyfin (or Plex) for you,
connects them to each other automatically, and gives you **one simple web page** to search,
request, download, watch progress, fix subtitles and check health.

You never copy an API key, pick a port, or edit a Docker network by hand.

> Status: **0.1 MVP**. It works end-to-end, but expect rough edges. See [What works today](#what-works-today).
> Only use Unifierr for media you are legally allowed to download.

## Why Unifierr?

| You want to… | Usually | With Unifierr |
|---|---|---|
| Install the apps | 6 compose files, ports, volumes | Tick boxes in a wizard |
| Connect them | Copy 5 API keys between 6 browser tabs | Done automatically |
| Get folders right for hardlinks | Read the TRaSH guide carefully | Prepared for you (`/data/torrents` + `/data/media`) |
| Use it every day | Open 6 different web UIs | One page: Discover, Requests, Downloads, Library, Health |
| Fix a problem | Read raw logs | Plain-English "what this means" and "how to fix" |

Unifierr does not replace these apps. It installs and drives the proven ones through their official APIs.
Dashboards like Homarr only link to apps, and Seerr only handles requests. Unifierr also does the setup,
the wiring and the daily operations. See [docs/RESEARCH.md](docs/RESEARCH.md).

## Install

You need a Linux machine or NAS with **Docker** (Synology, Unraid, TrueNAS SCALE or plain Linux).

The server image is not yet published to GHCR. For this preview, build from source:

```bash
git clone https://github.com/simplyzubair/unifierr.git
cd unifierr
docker compose --project-directory . -f deploy/docker-compose.yml -f deploy/docker-compose.build.yml up -d --build
```

The installer binds the web port to the server itself by default. Set up an HTTPS reverse proxy (for example, Tailscale Serve) to `http://127.0.0.1:8484`, then open its HTTPS address and follow the wizard. See [docs/INSTALL.md](docs/INSTALL.md) for access options.

1. **Create your admin account.**
2. **Check your system.** Unifierr detects your NAS type and Docker.
3. **Pick a storage folder.** Unifierr creates the right folder layout.
4. **Find apps you already have**, or tick the ones Unifierr should install.
5. **Connect everything.** One button: download client, indexers, subtitles and media server get wired together.
6. **Search and request** your first movie in *Discover*.

Platform notes (Synology, Unraid, TrueNAS), building from source, upgrades and backups:
**[docs/INSTALL.md](docs/INSTALL.md)**.

Windows, macOS, and Android client preview source: **[client/](client/)**. Client builds require access to
the NAS over Tailscale; requests and downloads continue to run on the server.

## What works today

| Area | Status |
|---|---|
| Setup wizard, environment detection (Synology/Unraid/TrueNAS/Linux) | ✅ |
| Install Radarr, Sonarr, Prowlarr, qBittorrent, SABnzbd, NZBGet, Bazarr, Jellyfin, Plex with Docker | ✅ |
| Detect and adopt existing installs, reading their API keys from their config files | ✅ |
| Auto-wiring: root folders, download client + categories (torrent or Usenet), Prowlarr → Radarr/Sonarr, Bazarr, Jellyfin/Plex libraries + refresh on import | ✅ |
| Discover/search, requests with approval for non-admin users | ✅ |
| Downloads (pause/resume/remove), indexers, subtitles, library, storage, health | ✅ |
| Update / restart / logs for apps Unifierr installed | ✅ |
| Backup and restore of Unifierr's own data | ✅ |
| Usenet download clients (SABnzbd, NZBGet) with a download-client picker | ✅ |
| VPN container (Gluetun) routing for download clients | ✅ |
| Multiple Radarr/Sonarr instances (named instances, per-instance wiring) | ✅ backend + API; instance UI is a follow-up |
| Plex first-time claim from the wizard | ✅ |
| Quality profiles / TRaSH custom formats | ✅ opt-in (Settings → Network → "Use TRaSH-Guides quality profiles") |

## Safety promises

- Unifierr **never deletes or changes** containers it did not create. "Forget" only removes the connection.
- It never overwrites an existing app's config files, and never touches your media files.
- Updates keep the old container until the new one runs, and roll back if it fails.
- All API keys and passwords are **encrypted** in Unifierr's database. Apps it installs get random passwords.

## Security

Unifierr can control Docker, so treat its admin password like a server password.
For access from outside your home, use **Tailscale** or a **Cloudflare Tunnel**. Never open port 8484 to the internet.
Details: [docs/SECURITY.md](docs/SECURITY.md).

## For developers

- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Contracts between modules: [docs/CONTRACTS.md](docs/CONTRACTS.md)
- Frontend notes: [docs/FRONTEND.md](docs/FRONTEND.md)
- Interactive API docs: `http://<server>:8484/api/docs`

```bash
# backend
cd backend && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest && .venv/bin/ruff check .
UNIFIERR_DATA_DIR=./data .venv/bin/uvicorn app.main:app --reload --port 8484
# frontend (proxies /api to :8484)
cd frontend && npm ci && npm run dev
```

## License

MIT
