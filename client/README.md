# Unifierr device client

The client is a small Windows, macOS, and Android app that opens the Unifierr
server's responsive web interface. The server and media services stay on your
NAS or computer; the client does not download media files onto the device.

## Connect to a server

1. Start the Unifierr server and make sure this device can reach it.
2. For a private NAS, install and connect Tailscale on this device, using the
   same tailnet as the NAS.
3. Open the client and enter the server's full HTTPS address, such as
   `https://unifierr.example.com`. Include a port or path only if your server
   setup uses one.
4. Select **Connect**, then sign in to Unifierr.

The address must use HTTPS and a certificate trusted by the device. The client
rejects addresses containing credentials, query strings, or fragments. It
remembers the last server address on this device; use **Clear saved address**
on the connect screen to remove it.

After connecting, the client loads the server website in its app window. It
does not provide a public relay or make a private server reachable from outside
its network.

## What happens to a request

The client sends a request to Unifierr on the server. Radarr or Sonarr and the
configured download client handle it there; completed media stays in the NAS
library and can be played through Jellyfin or Plex.

## Build installers

Install Node.js, Rust, and the platform tools required by Tauri 2. Use the
official Tauri prerequisites guide for the operating system you build on.

Install the client dependencies from this directory:

```sh
npm ci
```

Build the Windows installer (`.exe`, NSIS):

```sh
npm run build:windows
```

Build the macOS installer (`.dmg`):

```sh
npm run build:macos
```

Build an Android APK (debug signed for private testing):

```sh
npx tauri android init --ci
npm run build:android
```

Build outputs are under `src-tauri/target/` for desktop and
`src-tauri/gen/android/app/build/outputs/apk/` for Android. Windows and macOS
packages are unsigned; Android is a private test APK, not a Play Store build.
Production distribution needs platform signing and notarization.
