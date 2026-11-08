# Synology fresh install (preview)

This bundle starts a separate Unifierr container beside your existing media apps. It does not change Radarr, Sonarr, Prowlarr, qBittorrent, Bazarr, Jellyfin, or media files.

## Before installing

- This is a preview package for a **fresh Unifierr install**. Do not start it on a NAS that already has a Unifierr container using container name `unifierr` or port `8484`.
- The image is built for Linux x86-64. Check that your NAS supports that architecture.
- The Docker network containing your media apps must exist. The default is `media-stack`; change `UNIFIERR_DOCKER_NETWORK` in `.env` if your network has another name.
- The container has access to Docker's socket so Unifierr can discover and manage containers. Anyone who can administer Unifierr effectively has administrator access to Docker on this NAS.

## Install with Container Manager

1. In DSM File Station, create a folder such as `/volume1/docker/unifierr` and extract this ZIP into it.
2. Rename `.env.example` to `.env`. Set the timezone and existing Docker network name if needed.
3. In Container Manager, open **Image**, choose **Add > Add From File**, and import `unifierr-image.tar`.
4. Open **Project > Create**. Select the extracted folder as the project path and `portable-compose.yaml` as the compose file, then create the project.
5. Wait for the container health status to become healthy. The default web binding is NAS loopback only (`127.0.0.1:8484`).

## Secure access

Keep the default loopback binding. Use Tailscale Serve or a DSM reverse proxy with HTTPS to reach the app from other devices. Do not expose port 8484 directly to the internet. If your existing Unifierr already owns port 8484, stop here; use an in-place upgrade procedure instead of installing a duplicate.

Back up the project's `config` folder before future upgrades. The `data` folder is a separate Unifierr-managed storage root; existing media folders are not moved by this bundle.
