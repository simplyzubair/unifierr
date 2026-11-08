# Unifierr download page

This folder contains the static preview page intended for `unifierr.skillsgeek.com`.
The page links to assets attached to the private GitHub preview release
`client-v0.1.0`. Binary installers are intentionally excluded from Git; rebuild them
with `.github/workflows/client-build.yml` and attach the Windows, macOS, Android, and
checksum files to that release.

The server installer is not ready for a fresh NAS. See `SERVER-SETUP.md` for the
current limitations. Uploading the site files and configuring DNS are separate steps;
DNS alone does not host the page.

Windows and macOS preview installers are unsigned. The Android APK is a debug build
for ARM64 devices. Do not describe these as production releases.
