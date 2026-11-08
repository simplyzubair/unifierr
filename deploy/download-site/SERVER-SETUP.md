# Unifierr server package status

The server download is not ready for general NAS installation yet.

The repository does not currently contain a published, beginner-ready server image. The Synology trial configuration uses a locally built image and an existing Docker network, so distributing its Compose file by itself would not install Unifierr on a fresh NAS. Its machine-specific configuration is intentionally not copied into this public download bundle.

The Windows and Android client previews need a running Unifierr server. The client asks for the server address when it first opens; use an HTTPS address that the device can reach securely.

When the server image and general NAS setup are ready, this page should provide one server bundle, an editable Compose file, and a short setup and backup guide.
