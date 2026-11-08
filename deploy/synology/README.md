# Unifierr server for Synology

This Compose file runs Unifierr as a separate container beside the media apps
already installed on this NAS. It does not replace or reconfigure them.

## Before you start

- This is a private trial bundle for this NAS. It uses the local image
  `unifierr:local`; it is not yet a one-file installer for other NAS owners.
- Keep the NAS connected to Tailscale. From another device on your tailnet,
  open `https://synology-nas.tail594efe.ts.net`. Tailscale Serve should proxy
  this HTTPS hostname to `http://127.0.0.1:8484` on the NAS. If MagicDNS is
  disabled, use the HTTPS Tailscale hostname or configure Tailscale Serve first.
- Port 8484 is bound to NAS loopback only; Tailscale Serve provides the HTTPS
  relay. Do not expose this port through a public reverse proxy or tunnel.
- The Windows, macOS, and Android client source is in `client/`. Its first
  builds open this NAS's HTTPS address inside the app. Each client device must
  be connected to the same Tailscale network.

## What this creates

- A new Unifierr container named `unifierr`.
- Unifierr settings under `/volume1/docker/unifierr/config`.
- A separate data root at `/volume1/docker/unifierr/data`. Existing media in
  `/volume1/Media` is not moved or changed.
- A connection to the existing Docker network `media-stack` so Unifierr can
  reach supported apps by their container names.
- Read-only mounts of the Radarr, Sonarr, Prowlarr, and Bazarr configuration
  folders so Unifierr can look for existing API settings during adoption.

The Docker socket is mounted so Unifierr can inspect and manage containers.
Treat access to Unifierr as administrator-level access to Docker on this NAS.

## Start the trial

The image archive and Compose file must first be copied to
`/volume1/docker/unifierr` on the NAS. Then connect by SSH over Tailscale and
run:

```sh
cd /volume1/docker/unifierr
/usr/local/bin/docker load -i unifierr-image.tar
/usr/local/bin/docker compose -f unifierr-server.yaml up -d
```

Open `https://synology-nas.tail594efe.ts.net` from a device connected to the
same tailnet. Complete the first-run account setup, then inspect detected
apps. Do not select install, update, or other actions that would change
existing containers during this first check.

## Backups

Include `/volume1/docker/unifierr/config` in the NAS backup plan to preserve
Unifierr's database and settings. Continue backing up existing app settings
and `/volume1/Media` through the current NAS backup jobs.
