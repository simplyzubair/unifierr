# Unifierr Ecosystem & Competitive Research (Late 2026)

## 1. Existing Projects Analysis

| Project | What It Does | Install Method | Auto-Wires APIs | GUI Setup | License | Activity (Late 2026) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Dashboards** | | | | | | |
| [Homarr](https://github.com/homarr-labs/homarr) | Modular customizable dashboard with app widgets & status badges | Docker (Next.js/SQLite v1.0) | No (manual keys) | Yes | MIT | Very Active (v1.0 rewrite) |
| [Organizr](https://github.com/causefx/Organizr) | Tabbed iframe wrapper uniting self-hosted apps in one frame | Docker / Bare-metal (PHP) | No | Yes | GPL-3.0 | Maintenance / Slower |
| [Heimdall](https://github.com/linuxserver/Heimdall) | Lightweight application bookmark dashboard with badge stats | Docker / Bare-metal (PHP) | No | Yes | MIT | Maintenance |
| [Homepage](https://github.com/gethomepage/homepage) | High-performance, highly styled dashboard driven by YAML configs | Docker / Node.js | No (manual YAML) | No (YAML only) | GPL-3.0 | Very Active |
| **Request Managers** | | | | | | |
| [Seerr](https://github.com/seerr-team/seerr) | Unified media discovery & request portal (merged Overseerr + Jellyseerr, Feb 2026) | Docker / Bare-metal | No (manual *arr link) | Yes | MIT | Very Active (standard request hub) |
| [Ombi](https://github.com/Ombi-app/Ombi) | Classic feature-heavy request & issue tracking system for media stacks | Docker / Bare-metal (.NET) | No (manual *arr link) | Yes | GPL-3.0 | Active / Maintenance |
| [Doplarr](https://github.com/kiranshila/Doplarr) | Chatbot enabling media requests via Discord bot commands | Docker / Java JAR | No (manual env keys) | No (CLI/Bot) | AGPL-3.0 | Maintenance |
| **Installers & Stacks** | | | | | | |
| [YAMS](https://yams.media) | Guided bash script provisioning complete Docker media compose stack | Bash CLI script | No (manual web UI setup) | No (CLI prompts) | GPL-3.0 | Active |
| [DockSTARTer](https://github.com/GhostWriters/DockSTARTer) | Whiptail TUI shell script to generate and manage Docker Compose apps | Bash TUI | No | No (TUI only) | MIT | Low / Maintenance |
| [Saltbox](https://github.com/saltyorg/Saltbox) | Advanced Ansible playbooks for complete Ubuntu media/cloud automation | Ansible / CLI | Partial (Ansible vars) | No (CLI only) | GPL-3.0 | Active |
| [MediaStack](https://github.com/l4rm4nd/MediaStack) | Curated multi-container docker-compose media templates | Docker Compose | No | No (YAML files) | MIT | Maintenance |
| [TRaSH Guides](https://trash-guides.info) | Community reference guides & compose samples enforcing atomic paths | Documentation / Guides | N/A (Reference) | No | MIT / CC | Very Active |
| [Buildarr](https://github.com/buildarr/buildarr) | Declarative Configuration-as-Code for *arr stack REST APIs via YAML | Python CLI / Docker | Yes (declarative YAML) | No (YAML only) | GPL-3.0 | Active |
| [Recyclarr](https://github.com/recyclarr/recyclarr) | CLI synchronizer for TRaSH custom formats & quality profiles into *arr | Standalone CLI / Docker | No (profiles only) | No (CLI only) | MIT | Active |
| [Unmanic](https://github.com/Unmanic/unmanic) | Automated background media library video/audio transcode optimizer | Docker | N/A (Transcoder) | Yes | GPL-3.0 | Active |
| [Cosmos Cloud](https://github.com/azukaar/cosmos-server) | Self-hosted server suite, reverse proxy, 2FA, and Docker app market | Docker / Binary | No (isolated apps) | Yes | Apache-2.0 | Active |
| [CasaOS / ZimaOS](https://github.com/IceWhaleTech/CasaOS) | Elegant personal cloud web OS with 1-click Docker app store | Bare-metal install script | No (isolated apps) | Yes | Apache-2.0 | Very Active |
| [Unraid CA](https://unraid.net) | Unraid Community Applications Docker app catalog | Web GUI Plugin | No (manual app setup) | Yes | Proprietary | Very Active |
| [TrueNAS Apps](https://www.truenas.com) | SCALE Docker/Compose catalog for automated container deployment | Web GUI Catalog | No (manual app setup) | Yes | Open Source | Active |
| **Auto-Config Scripts** | | | | | | |
| [Flemmarr](https://github.com/Flemmarr/Flemmarr) | Ephemeral container applying YAML payloads to *arr REST APIs on startup | Docker container | Yes (via YAML files) | No (YAML only) | MIT | Maintenance |
| [servarr-setup / scripts](https://github.com/search?q=servarr+setup+script) | Ad-hoc user shell/python scripts calling curl or modifying sqlite | Bash / Python scripts | Partial (fragile) | No (CLI) | Unlicensed/Misc | Stale / Abandoned |

---

## 2. Gaps Unifierr Fills

| Feature / Need | Typical Dashboard (Homarr, Homepage) | Request Hub (Seerr) | Installer Scripts (YAMS, Saltbox) | Config-as-Code (Buildarr, Flemmarr) | App Stores (CasaOS, Unraid) | **Unifierr** |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Single Container Footprint** | Separate container | Separate container | Deploys 8+ containers | CLI/Config container | Full OS / Daemon | **Single container + web UI** |
| **Guided First-Run Web Wizard** | Manual widget setup | Connect wizard only | Terminal/CLI prompts | Text file editing | 1-click install per app | **Visual 5-step guided wizard** |
| **Zero-Touch API Inter-Wiring** | None (manual keys) | Manual *arr API keys | None (manual *arr setup) | High (requires YAML) | None | **Automated via internal API** |
| **Prowlarr App & Indexer Sync** | Read-only stats | None | Manual UI pairing | Via YAML declarations | None | **Automated sync to Radarr/Sonarr** |
| **Download Client Auto-Wiring** | Read-only queue widget | None | Manual IP & credentials | Via YAML declarations | None | **Auto-adds qBittorrent + categories** |
| **Bazarr & Subtitle Linking** | Link widget only | None | Manual API integration | Limited | None | **Auto-links Sonarr/Radarr to Bazarr** |
| **Media Server Integration** | Status widget only | Jellyfin/Plex request hub | Manual connection | Basic | None | **Auto-notifies Jellyfin/Plex on import** |
| **Single UI for Search & Queues**| Read-only status | Requests only | 6+ raw web UIs | No UI | 6+ separate web UIs | **One unified UI for daily media ops** |
| **TRaSH Atomic Path Enforcement** | N/A | N/A | Script dependent | None | Template dependent | **Pre-configured unified data volume** |

---

## 3. Critical Technical & Operational Risks

1. **Docker Socket Exposure (`/var/run/docker.sock`)**:
   - *Risk:* Mounting the Docker socket grants root-equivalent control over the host. Vulnerabilities in Unifierr's web API could allow remote container breakout or host compromise.
   - *Mitigation:* Support and recommend a read-only Docker socket proxy ([tecnativa/docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy)) restricting endpoints to container creation and inspection, or support rootless Docker / Docker API socket tokens.

2. **qBittorrent v5.0+ API Breaking Changes**:
   - *Risk:* qBittorrent v5.0+ removed the legacy `pause`/`resume` terminology across all API endpoints:
     - Old: `/api/v2/torrents/pause` $\rightarrow$ New: `/api/v2/torrents/stop`
     - Old: `/api/v2/torrents/resume` $\rightarrow$ New: `/api/v2/torrents/start`
     - Query filters: `filter=paused` was changed to `filter=stopped`, and torrent adding now uses `stopped=true`. Calling v4 endpoints on v5 results in `404 Not Found`.
   - *Mitigation:* Version-detect qBittorrent via `GET /api/v2/app/version` and branch adapter methods accordingly.

3. **Sonarr v4 API Divergence & Strict Auth**:
   - *Risk:* Sonarr v4 dropped all legacy `/api/` (v2 fallback) routes in favor of strict `/api/v3/`. Language profiles (`/api/v3/languageprofile`) were deleted and merged into Custom Formats and Quality Profiles (`formatItems`). Mandatory authentication cannot be disabled out of the box, requiring immediate API key extraction before any calls succeed.
   - *Mitigation:* Target Sonarr `/api/v3` endpoints exclusively, omit deprecated `languageProfileId`, and read keys directly from `/config/config.xml` during container discovery.

4. **Atomic Moves & Hardlinks (The "Cross-Device" Path Trap)**:
   - *Risk:* If downloads and media libraries are mapped under separate container volumes (e.g., `-v /data/downloads:/downloads` and `-v /data/media:/media`), Linux treats them as distinct filesystems. Moving completed downloads forces a slow, intensive I/O copy + delete rather than an instantaneous atomic hardlink (`st_dev` mismatch).
   - *Mitigation:* Strictly adhere to [TRaSH Guides single-volume standard](https://trash-guides.info/Hardlinks/How-to-setup-for/Docker/): mount one single root directory (e.g., `/data`) with subpaths `/data/torrents` and `/data/media`.

5. **Port Clashes & Network Routing in Bridged Containers**:
   - *Risk:* Running alongside existing setups or VPN containers (e.g. Gluetun) causes name-resolution and port conflicts (e.g. qBittorrent default `8080`, Radarr `7878`, Sonarr `8989`).
   - *Mitigation:* Use an internal isolated bridge network (`unifierr-network`) using internal container DNS names (`http://sonarr:8989`) rather than host loopback IPs.

---

## 4. Five Concrete UX Lessons to Adopt

1. **Seerr's Instant Media Card & Request Modal**:
   - *Lesson:* Avoid exposing raw technical metadata (profiles, indexer IDs, path selectors) to normal users. Provide a clean media card with a single "Request" button that automatically selects standard profiles and default root folders, with an optional expandable "Advanced" drawer for power users.

2. **Prowlarr's "Test & Sync All" Feedback Loop**:
   - *Lesson:* Multi-app configuration often fails invisibly. Implement Prowlarr's pattern: an explicit "Test Connection" button on every adapter with a live spinner that resolves to a clear green checkmark or an actionable, plain-English troubleshooting tip. Include an idempotent "Sync All" button that reconciles all links in one click.

3. **Consolidated Queue & Download Controls (Flood / qBittorrent UX)**:
   - *Lesson:* Users switch tabs constantly to check download speeds or pause stuck torrents. Incorporate a unified bottom or slide-out tray displaying active download progress, global speeds, ETA, and one-click pause/resume/delete actions across all clients.

4. **Homarr / CasaOS High-Level Health & Storage Badges**:
   - *Lesson:* Do not force users to drill into individual service status pages. Show high-level system cards on the dashboard: disk space remaining per media root, aggregate VPN/Internet status, and color-coded alert badges (healthy, warning, offline) with plain-English resolution steps.

5. **Frictionless Zero-Key First-Run Wizard**:
   - *Lesson:* Users hate copy-pasting 5 hex API keys across 6 browser tabs. The setup wizard must automatically inspect Docker volumes to read `config.xml` / `config.ini` files, auto-populate API keys, propose standardized TRaSH paths, and complete wiring with a single "Apply & Launch" action.
