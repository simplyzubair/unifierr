# Unifierr Frontend Architecture & Guide

The Unifierr web frontend is a modern, single-page application (SPA) built for extreme simplicity and beginner friendliness. It enables users to deploy, monitor, and use a self-hosted media stack (Radarr, Sonarr, Prowlarr, qBittorrent, Bazarr, Jellyfin/Plex) without dealing with raw API keys, ports, or Docker network configurations.

---

## 1. Stack & Design Choices

* **Framework:** React 18 with TypeScript in `strict` mode.
* **Build Tool:** Vite 5 (outputs static files to `frontend/dist`).
* **Styling:** Tailwind CSS v3 with PostCSS and class-based dark mode (`dark` by default, persisted in `localStorage` with `try/catch` guard).
* **Routing:** `react-router-dom` (BrowserRouter with backend fallback to `index.html`).
* **Server State:** `@tanstack/react-query` v5 for caching and query management.
* **Icons:** `lucide-react`.
* **Testing:** Vitest + `@testing-library/react` + `@testing-library/jest-dom` + `jsdom`.
* **Linting:** ESLint 9 + `typescript-eslint`.

---

## 2. File & Directory Layout

```
frontend/
├── dist/                      # Static production build served by FastAPI at "/"
├── public/
│   └── logo.svg               # SVG brand mark
├── src/
│   ├── api/
│   │   ├── client.ts          # Base fetch client (credentials, CSRF header, ErrorCard parser)
│   │   └── index.ts           # Typed endpoint modules matching CONTRACTS.md
│   ├── components/
│   │   ├── common/
│   │   │   ├── Badge.tsx      # Availability badges (Available, Downloading, Requested, etc.)
│   │   │   ├── ConfirmDialog.tsx # Safe destructive action dialogs with optional checkbox
│   │   │   ├── EmptyState.tsx # Friendly plain-English empty states
│   │   │   ├── ErrorCard.tsx  # Error cards with message, "What this means", and "How to fix"
│   │   │   ├── Logo.tsx       # Inline SVG brand mark + typography
│   │   │   ├── Modal.tsx      # Accessible dialog modals with Escape and backdrop support
│   │   │   ├── ProgressBar.tsx# ARIA-accessible progress indicators
│   │   │   ├── Skeleton.tsx   # Loading placeholders for cards, tables, posters
│   │   │   └── Tooltip.tsx    # One-liner technical jargon dictionary & tooltips
│   │   └── layout/
│   │       └── AppShell.tsx   # Responsive desktop sidebar / mobile drawer & topbar
│   ├── context/
│   │   ├── AuthContext.tsx    # Auth state, session status, role-based guard (admin/user)
│   │   └── ThemeContext.tsx   # Dark/light mode state (localStorage try/catch)
│   ├── pages/
│   │   ├── auth/
│   │   │   ├── Bootstrap.tsx  # First-run admin account creation screen (POST /api/auth/bootstrap)
│   │   │   └── Login.tsx      # Login screen with status detection
│   │   ├── discover/
│   │   │   └── Discover.tsx   # Debounced search, media cards, request modal, recent media
│   │   ├── downloads/
│   │   │   └── Downloads.tsx  # 3s polling, speed totals, ETA, pause/resume/delete
│   │   ├── health/
│   │   │   └── Health.tsx     # Overview banner, per-service status, disk bars, event log
│   │   ├── indexers/
│   │   │   └── Indexers.tsx   # Prowlarr indexers, enable toggle, schema catalog search & add
│   │   ├── library/
│   │   │   └── Library.tsx    # Movie & TV tabs, missing/available filters, size on disk
│   │   ├── requests/
│   │   │   └── Requests.tsx   # Status filters, admin approve/deny with note, delete
│   │   ├── settings/
│   │   │   └── Settings.tsx   # Apps management, user management, password change, backup/restore
│   │   └── setup/
│   │       └── SetupWizard.tsx# 6-step setup stepper (Env, Storage, Apps, Install, Wire, Done)
│   ├── test/
│   │   ├── apiClient.test.ts  # CSRF header injection & error parsing tests
│   │   ├── badge.test.tsx     # Availability badge test suite
│   │   ├── setup.ts           # Vitest DOM cleanup setup
│   │   └── wizard.test.tsx    # Setup wizard stepper navigation tests
│   ├── types/
│   │   └── api.ts             # TypeScript models matching backend pydantic schemas
│   ├── App.tsx                # Route definitions and role-based Route Guards
│   ├── index.css              # Tailwind base, utilities, and scrollbar styles
│   └── main.tsx               # Application entrypoint
├── eslint.config.js           # Flat ESLint configuration
├── index.html                 # HTML root
├── package.json
├── postcss.config.js
├── tailwind.config.js
├── tsconfig.json
└── vite.config.ts             # Dev proxy (/api -> http://127.0.0.1:8484) & Vitest config
```

---

## 3. API Client & Security Rules

1. **CSRF Protection:**
   Every non-`GET` request (`POST`, `PUT`, `PATCH`, `DELETE`) automatically sends the header:
   `X-Unifierr-CSRF: 1`.

2. **Credentials:**
   `credentials: 'same-origin'` is sent on every request to pass the `unifierr_session` httpOnly cookie.

3. **Authentication Handshake:**
   - On 401 Unauthorized responses, the client safely redirects to `/login`.
   - On initial load, `/api/setup/status` determines whether an admin account exists (`has_admin: false` routes directly to the Bootstrap screen).

4. **Friendly Error Parsing:**
   Backend error payloads (either `{detail: string}` or `{error: string, explanation: string, fix: string}`) are parsed into `ApiError` instances and rendered via `ErrorCard` with clear "What this means" and "How to fix" sections.

---

## 4. Development & Build Commands

```bash
cd frontend

# Install dependencies
npm install

# Run dev server (proxies /api to http://127.0.0.1:8484)
npm run dev

# Run unit & integration test suites
npm test

# Run ESLint validation
npm run lint

# Production TypeScript typecheck & Vite build
npm run build
```
