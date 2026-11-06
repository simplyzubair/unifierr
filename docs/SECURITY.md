# Security model

**Who can do what**
- One or more **admins** run setup and manage apps, downloads, indexers, users and backups.
- **Users** can search, request media (an admin approves it) and see the library. They only see their own requests.
- Every API route checks the role on the server. Hiding a button in the UI is never the only protection.

**Sign-in**
- Passwords are hashed with Argon2. Sessions are random tokens stored hashed on the server, in an
  `HttpOnly`, `SameSite=Strict` cookie. Changing your password signs out your other devices.
- Failed sign-ins are rate-limited (10 per 5 minutes per IP and username).
- State-changing requests need the `X-Unifierr-CSRF: 1` header (forged cross-site requests can't send it).
- Behind HTTPS, set `UNIFIERR_SECURE_COOKIES=true`.

**Secrets**
- API keys and passwords of connected apps, VPN credentials, WireGuard keys, and Plex claim tokens are
  encrypted with Fernet (AES-128-CBC + HMAC).
  The key lives in `config/secret.key` (mode 600), or comes from `UNIFIERR_SECRET_KEY`.
- Secrets are never returned by the API, except the "Show login" button for logins Unifierr created
  (admin only; every view is written to the event log). Logs shown in the UI are redacted.
- Apps installed by Unifierr always require a login. Unifierr generates a random one for each.

**Docker**
- Unifierr only restarts, updates or reads logs of containers it created (label `io.unifierr.managed=true`).
- Mounting the Docker socket is root-equivalent. Use the socket proxy in INSTALL.md if you want to limit it.

**Web hardening**
- Content-Security-Policy, `X-Frame-Options: DENY`, `nosniff`, `no-store` on API responses.
- Backups are validated before restore (zip structure, SQLite integrity, expected tables). Sessions in the
  backup are discarded.

**Remote access**
Use Tailscale or Cloudflare Tunnel (with Cloudflare Access). Do not port-forward 8484.

Report vulnerabilities privately through GitHub Security Advisories.
