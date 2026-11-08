# Synology server bundle

The downloadable fresh-install preview bundle contains a prebuilt `linux/amd64` image, `portable-compose.yaml`, and `.env.example`. Follow [INSTALL-SYNOLOGY.md](INSTALL-SYNOLOGY.md).

It uses the existing Docker network named `media-stack` by default so it can reach an existing media stack. Set `UNIFIERR_DOCKER_NETWORK` to the network name on your NAS if it differs. The service listens on NAS loopback port `8484`; use Tailscale Serve or an HTTPS reverse proxy for other devices.

This is not an in-place upgrade bundle. If Unifierr is already installed, keep its existing config backed up and do not start another container with the same name or port.
