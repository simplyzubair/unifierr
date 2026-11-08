# Download site deployment

The `unifierr.skillsgeek.com` hostname uses a dedicated Nginx site on the SkillsGeek VPS. Its `current` symlink points to a versioned static release:

```text
/var/www/unifierr/current -> /var/www/unifierr/releases/<release>/
  index.html
  downloads/
    SHA256SUMS.txt
    unifierr-windows-preview-0.1.3.exe
    unifierr-macos-preview-0.1.3.dmg
    unifierr-android-arm64-preview-0.1.3.apk
    unifierr-synology-server-preview-0.1.0.zip
```

Upload the next site and download files into a new release directory, verify the checksums, then atomically update `current`. The Nginx virtual host is included in [nginx.conf](nginx.conf); it redirects HTTP to HTTPS and serves static files only. The matching certificate is managed by Certbot.

Do not change the VPS default virtual host; it belongs to another site. `index.html` has no client-side script or external runtime dependencies. Recalculate `SHA256SUMS.txt` whenever a download changes.
