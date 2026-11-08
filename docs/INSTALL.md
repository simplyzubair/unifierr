# Installing, upgrading and backing up Unifierr

## Before you start

- A NAS or Linux machine with **Docker Engine**. The Compose workflow varies by platform: Synology Container Manager supports Projects, Unraid needs a community Compose plugin or manual container templates, and TrueNAS uses its advanced **Install via YAML** flow.
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

Compose binds port 8484 to `127.0.0.1` on the server by default. For access from another device, configure an HTTPS reverse proxy such as Tailscale Serve to forward to `http://127.0.0.1:8484`. Do not forward port 8484 from your router to the internet.

## Verification status (November 8, 2026)

- An existing Synology trial instance is responding: its health endpoint returned `{"status":"ok","version":"0.1.0"}`. This confirms that earlier image is running; the current checkout changes have **not** been deployed to that NAS.
- The current checkout built as a Linux/amd64 image on Docker Desktop Engine 29.9.2. Its container reached `healthy`, `/api/health` returned `status: ok`, and the frontend root page loaded.
- The production Compose file and source-build override parsed successfully. Installer path/health checks and the Compose environment-path test passed locally.
- Anonymous access to `ghcr.io/simplyzubair/unifierr:latest` was denied, and no version tags were present. A public, versioned server image is not ready for a beginner pull install.
- Unraid and TrueNAS instructions have not been smoke-tested on those devices. A successful YAML parse is not a substitute for testing their host permissions and Docker socket behavior.
- The release workflow publishes the image only after a version tag is pushed; no image built from these worktree changes has been published.

Treat the platform steps below as installation guidance, not proof of a completed release on every NAS.

## Standard Linux

These commands use `ghcr.io/simplyzubair/unifierr:latest`. They work only after a version release has been published and the GHCR package is public. Until then, use [Build from source](#build-from-source).

```bash
mkdir -p ~/unifierr && cd ~/unifierr
curl -fsSLO https://raw.githubusercontent.com/simplyzubair/unifierr/feat/unifierr-mvp/deploy/docker-compose.yml
curl -fsSL  https://raw.githubusercontent.com/simplyzubair/unifierr/feat/unifierr-mvp/deploy/.env.example -o .env
# edit .env: UNIFIERR_ROOT=/srv/unifierr, PUID/PGID from the `id` command, TZ=Europe/London
sudo mkdir -p /srv/unifierr && sudo chown $(id -u):$(id -g) /srv/unifierr
docker compose up -d
```

Or run `deploy/install.sh`, which checks Docker first. It uses `/srv/unifierr` by default; set `UNIFIERR_ROOT` to an absolute host path before running it to choose another storage location. The installer preserves an existing `.env` file.

## Synology (DSM 7.2+)

1. Install **Container Manager** from Package Center.
2. Create a dedicated shared folder for Unifierr's app data and managed media, for example `unifierr` (usually `/volume1/unifierr`). If you already have a media library, leave it in place; connect its existing apps during setup instead of moving or changing the library.
3. In that folder, create a project folder such as `docker/unifierr`. Download `deploy/docker-compose.yml` and `deploy/.env.example` from the same Unifierr release into it; rename `.env.example` to `.env`.
4. Edit `.env` and set `UNIFIERR_ROOT` to the dedicated folder from step 2. Set `PUID` and `PGID` to the IDs that have write access to that folder. You can check them over SSH with `id`; DSM commonly uses UID `1026` and GID `100`, but verify yours.
5. In Container Manager, open **Project → Create**, choose the project folder from step 3, review the compose file and environment values, then start the project.
6. Keep `UNIFIERR_BIND_ADDRESS=127.0.0.1`. Configure Tailscale Serve or another HTTPS reverse proxy to forward to `http://127.0.0.1:8484`, then open its HTTPS address and follow the setup wizard. See [SECURITY.md](SECURITY.md).

## Unraid

Unraid does not include Docker Compose in its built-in Docker interface. The steps below use **Compose Manager Plus**, a community plugin, so check its current compatibility notes before installing it. Unraid's built-in container templates remain the alternative for users who do not want a community plugin, but setting up this multi-container stack through templates is manual.

1. Choose a share path such as `/mnt/user/unifierr` for Unifierr data; avoid a disk-specific path such as `/mnt/disk1/...`.
2. Use the UID/GID defaults `99`/`100` if those match your share permissions.
3. Install the community Compose Manager plugin using its [current installation guide](https://github.com/mstrhakr/compose_plugin). Its current project page lists Unraid 7.2.3 and later as verified. The plugin's Community Applications availability has changed over time, so use the manual plugin URL shown by its guide if it is not listed in the Apps tab.
4. Copy `deploy/.env.example` to `.env` in the plugin's project folder and set `UNIFIERR_ROOT=/mnt/user/unifierr`, `PUID=99`, and `PGID=100`. Compose Manager Plus stores the stack's `.env` alongside its project. Keep the host and container storage paths identical.

References: [Unraid Docker overview](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/overview/) and [Compose Manager Plus](https://github.com/mstrhakr/compose_plugin).

## TrueNAS SCALE (Docker-based Apps)

TrueNAS uses Docker-based Apps and supports third-party applications through **Install via YAML**. This is an advanced Compose editor, not a normal project-folder install.

1. Create a dedicated dataset for Unifierr before starting the app wizard, for example `/mnt/tank/unifierr`. Do not point it at an existing library root.
2. Give the dataset write access for the UID/GID you plan to use (commonly `568`/`568`). Before opening the app wizard, create the database directory in the TrueNAS CLI: `storage filesystem mkdir path="/mnt/tank/unifierr/appdata/unifierr"`.
3. In **Apps → Discover**, choose **Install via YAML** and paste the Compose configuration.
4. The YAML editor does not automatically use the downloaded `.env.example`. Replace every `${UNIFIERR_ROOT:-/srv/unifierr}` occurrence with the absolute dataset path, such as `/mnt/tank/unifierr`. Replace `./config:/config` with `/mnt/tank/unifierr/appdata/unifierr:/config`. Keep the storage root identical inside and outside the container.
5. Keep `PUID` and `PGID` set to the IDs with dataset write access. For the simple install path, use a published production image. The YAML editor can build from a Dockerfile only when its build context and Dockerfile are available on the NAS; the steps above do not transfer the source checkout.

TrueNAS requires host-path directories and permissions to be prepared before deployment. See its [Custom Apps guide](https://apps.truenas.com/managing-apps/installing-custom-apps/) for the current wizard and storage options.

## Build from source

```bash
git clone https://github.com/simplyzubair/unifierr && cd unifierr
docker compose --project-directory . -f deploy/docker-compose.yml -f deploy/docker-compose.build.yml up -d --build
```

## Publishing a prebuilt image

The release workflow builds the image and pushes it to GitHub Container Registry (GHCR). It first runs the same
backend, frontend, Compose, image-build, and container smoke checks as CI.

- Pushing a version tag such as `v0.1.0` publishes that version plus `latest` for `linux/amd64` and `linux/arm64`.
- Pushing to `main` or `feat/unifierr-mvp` publishes `latest` (and a `sha-<commit>` tag) for `linux/amd64` only, so
  a server with automatic updates follows every push.

The first GHCR package is private by default. Either make it public in GitHub's package settings (GitHub does not
allow making a public package private again) or give the server a login that can read it: add
`UNIFIERR_REGISTRY_USER` and `UNIFIERR_REGISTRY_TOKEN` (a personal access token with only `read:packages`) to the
server's environment. To use another registry, set `UNIFIERR_IMAGE` in `.env`, for example
`UNIFIERR_IMAGE=docker.io/<you>/unifierr:latest`.
See [GitHub's package visibility documentation](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility).

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
peer port (6881/tcp and 6881/udp) through the VPN container. Service management screens stay on the private
Docker network; Unifierr connects to them without asking you to configure their ports. Jellyfin or Plex keeps
its streaming endpoint available to media clients, because those clients connect to the media server itself.

## Ports and client devices

The default Compose setup listens on the NAS itself at `127.0.0.1:8484`. From Android, macOS, Windows,
Linux, or another device, use an HTTPS reverse proxy that forwards to that local address. Keep the
management engines on their internal Docker ports; those ports are private by
default. Jellyfin/Plex clients still connect to the media server's streaming endpoint (Jellyfin uses 8096 by
default). Unifierr configures these connections during setup; users do not need to enter service ports or API
keys in the wizard. Existing containers keep their current port bindings when Unifierr adopts them.

The first native client preview is in [`client/`](../client/). It opens this NAS's HTTPS Tailscale address in
an app window; the device must be signed in to the same tailnet. Download jobs still run on the NAS, and
completed media stays in its library. This preview is tied to this NAS and is not yet a general-purpose
client for choosing different Unifierr servers.

## Updating Unifierr

Open **Updates** in the menu. **Check for updates** looks for a newer image under the same tag Unifierr is running
from; **Update now** installs it. Tick **Update automatically** and Unifierr checks every 15 minutes
(`UNIFIERR_UPDATE_CHECK_SECONDS`) and installs a new version by itself.

How it works: Unifierr pulls the newer image, then starts a short-lived helper container from it. The helper stops
Unifierr, recreates it with the same settings (ports, folders, network, `extra_hosts`, environment), and waits until
the new container reports healthy. If it does not, the old container is started again and the Updates page says so.
An image that failed is not retried by automatic updates. Your database and settings live in `./config` and are
never touched. Downloads keep running; only the Unifierr page is away for about a minute.

Requirements: Unifierr must run from a registry image (not an imported `unifierr:local` file), and the Docker
socket must be mounted. The Updates page explains what is missing. The phone, tablet and computer apps show the
server's website, so they get new screens as soon as the server updates; a new app file is only needed when the
app itself changes.

If the power fails or Docker is killed in the few seconds between stopping the old Unifierr and starting the new
one, Unifierr can be left stopped. Nothing is lost (your data lives in `./config`), and the previous version is
still on disk under the name `unifierr-old`. Bring it back with:

```bash
docker rm -f unifierr 2>/dev/null; docker rename unifierr-old unifierr && docker start unifierr
```

To update by hand instead:

```bash
cd ~/unifierr
docker compose pull && docker compose up -d
```

Database changes are applied automatically on start.

## Upgrading the apps

Settings → Apps → **Update** (only for apps Unifierr installed). The old container is kept until the new one runs,
and it is restored automatically if the update fails.

## Backup and restore

- Settings → Backup → **Download backup**. You get a `.zip` with Unifierr's database and its encryption key.
  **Keep it private**: it can decrypt the saved API keys.
- To restore: Settings → Backup → **Restore** and choose the zip. The previous database is kept as
  `config/unifierr.db.before-restore-<time>`.
- Your apps keep their own settings in `UNIFIERR_ROOT/appdata`. Back up that folder with your NAS backup tool too.

## Optional: Docker socket endpoint proxy (advanced)

Mounting `/var/run/docker.sock` gives Unifierr administrator-level control over Docker and the NAS. An endpoint proxy can hide Docker API endpoints that Unifierr does not use, but it is **not a strong security boundary**: enabling container creation still allows powerful host-level actions. Run
[tecnativa/docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy) with
`CONTAINERS=1 IMAGES=1 NETWORKS=1 POST=1 INFO=1` on the private `unifierr` Docker network. Do not
publish the proxy's port. Remove the socket line from Unifierr's Compose file and set
`UNIFIERR_DOCKER_HOST=tcp://docker-socket-proxy:2375` in `.env`; Compose passes this setting into the
container. Keep Unifierr available only to trusted administrators.

## Troubleshooting

| Problem | Fix |
|---|---|
| Wizard says "Docker is not available" | The `/var/run/docker.sock` line is missing from the compose file, or Docker is not running. |
| "Port … is already in use" | You already run that app or another program on that port. Connect the existing app instead. |
| Folder not writable | Check `PUID`/`PGID` and the NAS shared-folder permissions or dataset ACL. Grant access to Unifierr's dedicated folder through DSM permissions. Avoid recursive ownership changes on an existing media library. |
| Hardlinks warning | `data/torrents` and `data/media` are on different disks or shares. Put both in one share. |
| Anything else | Health page, then Settings → Apps → **View logs**. |
