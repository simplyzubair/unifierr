# Download site deployment

The domain's DNS currently points to the existing SkillsGeek VPS, which also serves `noterr.skillsgeek.com`. Install this site's files under a dedicated Nginx host root for `unifierr.skillsgeek.com`; do not replace the default root or another app's vhost.

Expected layout:

```text
/var/www/unifierr/
  index.html
  downloads/
    SHA256SUMS.txt
    unifierr-windows-preview-0.1.2.exe
    unifierr-macos-preview-0.1.2.dmg
    unifierr-android-arm64-preview-0.1.2.apk
    unifierr-synology-server-preview-0.1.0.zip
```

The TLS certificate is issued for `unifierr.skillsgeek.com` with Certbot after the dedicated Nginx host is enabled. Do not serve the preview through the default virtual host; the default host currently belongs to another site.

`index.html` is static and has no client-side script or external runtime dependencies. Recalculate `SHA256SUMS.txt` whenever any published download changes.
