# Installing, upgrading and backing up Unifierr

## Before you start

- A machine with **Docker** and **Docker Compose** (built into Synology Container Manager, Unraid, TrueNAS SCALE apps).
- One folder for everything (apps' settings, downloads and media). It is called **`UNIFIERR_ROOT`**.
  Unifierr creates this layout inside it:

```
UNIFIERR_ROOT/
├── appdata/radarr, sonarr, ...   settings of each app
└── data/
    ├── torrents/movies, tv        downloads in progress
    └── media/movies, tv           your library (Jellyfin/Plex read this)
```

Downloads and media live under one `data` folder on purpose. Then finished downloads are
*hardlinked* into your library instantly, with no copying and no double disk usage.

## Standard Linux

```bash
mkdir -p ~/unifierr && cd ~/unifierr
curl -fsSLO https://raw.githubusercontent.com/simplyzubair/unifierr/main/deploy/docker-compose.yml
curl -fsSL  https://raw.githubusercontent.com/simplyzubair/unifierr/main/deploy/.env.example -o .env
# edit .env: UNIFIERR_ROOT=/srv/unifierr, PUID/PGID from the `id` command, TZ=Europe/London
sudo mkdir -p /srv/unifierr && sudo chown $(id -u):$(id -g) /srv/unifierr
docker compose up -d
```

Or run `deploy/install.sh`, which does the same steps and checks Docker first.

## Synology (DSM 7.2+)

1. Install **Container Manager** from Package Center.
2. In File Station, create a shared folder, e.g. `/volume1/media`. Set `UNIFIERR_ROOT=/volume1/media`.
3. Find your user's IDs: SSH in and run `id` (often `uid=1026 gid=100`). Put them in `PUID`/`PGID`.
4. Container Manager → **Project** → Create → upload `docker-compose.yml` and `.env` → Start.

## Unraid

Use a share such as `/mnt/user/media` as `UNIFIERR_ROOT` (not a disk path like `/mnt/disk1`).
Defaults: `PUID=99`, `PGID=100`. Install the *Docker Compose Manager* plugin and add the stack.

## TrueNAS SCALE (24.10+)

Create a dataset, e.g. `/mnt/tank/media`, and give your apps user (UID `568`) modify rights on it.
Set `UNIFIERR_ROOT=/mnt/tank/media`, `PUID=568`, `PGID=568`, then install with *Apps → Discover → Custom App (YAML)*.

## Build from source

```bash
git clone https://github.com/simplyzubair/unifierr && cd unifierr
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.build.yml up -d --build
```

## Plex

When you choose to install a new Plex server in the setup wizard, create a claim token at
<https://plex.tv/claim> and paste it into the **Network & Plex** step immediately before installation. Tokens
expire after about four minutes. Unifierr encrypts the token at rest and supplies it to Plex for its first start;
it is not written to Unifierr's event log. If Plex is already running, adopt it instead—the wizard will not
rewrite its container or configuration. Jellyfin needs no claim token and remains the recommended choice for
beginners.

## Optional: route downloads through a VPN

Enable **Route downloads through VPN** in the setup wizard or Settings → Network & VPN. Unifierr installs
Gluetun and places newly installed qBittorrent and Prowlarr containers in its network namespace. Select the VPN
provider name used by Gluetun and provide either OpenVPN credentials or a WireGuard private key. Credentials
are encrypted in Unifierr's database. Existing download apps and existing Gluetun containers are never
reconfigured; the Health page warns when qBittorrent cannot be reached through Gluetun. Gluetun publishes the
supported web ports (qBittorrent 8080, Prowlarr 9696, and the conventional SABnzbd/NZBGet ports) through the
VPN container.

## Upgrading Unifierr

```bash
cd ~/unifierr
docker compose pull && docker compose up -d
```

Database changes are applied automatically on start. Your settings stay in `./config`.

## Upgrading the apps

Settings → Apps → **Update** (only for apps Unifierr installed). The old container is kept until the new one runs,
and it is restored automatically if the update fails.

## Backup and restore

- Settings → Backup → **Download backup**. You get a `.zip` with Unifierr's database and its encryption key.
  **Keep it private**: it can decrypt the saved API keys.
- To restore: Settings → Backup → **Restore** and choose the zip. The previous database is kept as
  `config/unifierr.db.before-restore-<time>`.
- Your apps keep their own settings in `UNIFIERR_ROOT/appdata`. Back up that folder with your NAS backup tool too.

## Optional: Docker socket proxy (stricter security)

Mounting `/var/run/docker.sock` gives Unifierr full control over Docker. To limit it, run
[tecnativa/docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy) with
`CONTAINERS=1 IMAGES=1 NETWORKS=1 POST=1 INFO=1`, remove the socket line from Unifierr's compose file,
and set `UNIFIERR_DOCKER_HOST=tcp://docker-socket-proxy:2375`.

## Troubleshooting

| Problem | Fix |
|---|---|
| Wizard says "Docker is not available" | The `/var/run/docker.sock` line is missing from the compose file, or Docker is not running. |
| "Port … is already in use" | You already run that app or another program on that port. Connect the existing app instead. |
| Folder not writable | `PUID`/`PGID` don't own `UNIFIERR_ROOT`. Run `sudo chown -R PUID:PGID UNIFIERR_ROOT`. |
| Hardlinks warning | `data/torrents` and `data/media` are on different disks or shares. Put both in one share. |
| Anything else | Health page, then Settings → Apps → **View logs**. |
