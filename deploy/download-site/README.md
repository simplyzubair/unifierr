# Unifierr downloads

This is the static page hosted at `unifierr.skillsgeek.com`. Download files live in the server's `/downloads/` directory and are deployed separately from Git so release binaries and the server image are not committed to source control.

The client downloads are preview builds from the `client-v0.1.7` release, copied to the public download host. Windows/macOS are unsigned and Android is an ARM64 debug APK. The Android build includes safe spacing around system navigation buttons. The Synology server archive is a fresh-install preview for `linux/amd64`; its guide describes its network and security requirements.

The host uses the dedicated [Nginx config](nginx.conf), an immutable release directory under `/var/www/unifierr/releases/`, and a `current` symlink for deployments. See [SERVER-SETUP.md](SERVER-SETUP.md).
