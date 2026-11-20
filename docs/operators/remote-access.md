# Remote Access — Animus on Your Phone

Access Animus from your phone securely using the **PWA** (the `packages/pwa`
mobile web app) reached over a **Tailscale** private network. No App Store, no
open public ports — your phone and your Animus box join a private, end-to-end
encrypted WireGuard mesh, and a bearer token adds defense in depth.

## Why this approach

- **PWA, not a native app.** The PWA installs to your home screen, runs
  full-screen, works offline, and supports push notifications (iOS 16.4+). One
  codebase across iOS / Android / desktop.
- **Tailscale, not port-forwarding.** Nothing is exposed to the public
  internet. Only devices on your tailnet can reach the dashboard.
- **Bearer token** on the PWA's API and chat WebSocket, with `auth_required =
  "always"` also protecting other dashboard routes.

## 1. Install Tailscale

Install on the Animus box **and** your phone, signed into the same tailnet:

```bash
# On the Animus box
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Install the Tailscale app on your phone and sign in. Enable **MagicDNS** and
**HTTPS** in the tailnet admin console (Settings → DNS). Your box now has a
stable name like `mybox.tailnet-name.ts.net`.

## 2. Serve the dashboard over HTTPS

A **secure context (HTTPS)** is required for the PWA service worker and Web
Push. A bare `100.x` tailnet IP over plain HTTP will **not** work — the service
worker and notifications silently fail. Use a real certificate from
`tailscale cert`.

### Recommended: terminate TLS in the dashboard (preserves real client IPs)

```bash
# Generate a cert for your machine's MagicDNS name
sudo tailscale cert mybox.tailnet-name.ts.net
```

Then point the dashboard at it and bind to the tailnet so remote clients keep
their real IPs (which is what makes the bearer token enforceable):

```toml
# ~/.config/animus/config.toml
[services]
host = "0.0.0.0"                 # reachable over the tailnet
auth_required = "always"         # enforce the bearer token
tls_cert = "/path/to/mybox.tailnet-name.ts.net.crt"
tls_key  = "/path/to/mybox.tailnet-name.ts.net.key"
```

> **Using `tailscale serve`:** the proxy connects to loopback, so configure
> `auth_required = "always"`. In this mode the bearer token is enforced even
> for loopback clients. With `"auto"`, loopback requests bypass bearer auth;
> do not use that mode behind a proxy unless its forwarded client identity is
> securely configured and verified.

Restart the dashboard. On first run with `auth_required` active it generates a
token and stores it in the protected `~/.config/animus/config.toml` file. The
token is never written to logs. Retrieve `services.auth_token` privately on
Stheno, then enter it on the phone's PWA login screen. Do not paste the token
into chat or include it in shell commands that are saved to history. To rotate
it, clear `services.auth_token` in the config and restart.

## 3. Build and serve the PWA

```bash
cd packages/pwa
npm install
npm run build      # outputs dist/
```

Set `ANIMUS_PWA_DIR` to the built `dist/` directory in the Animus service
environment. The app serves it at `/pwa/` on the dashboard origin; API and
WebSocket calls stay same-origin. The PWA shell and assets are public so the
login screen can load. Data and mutation routes still require the bearer token.

## 4. Install on your phone

1. On your phone (with Tailscale connected), open
   `https://mybox.tailnet-name.ts.net/pwa/`.
2. Paste the token on the login screen.
3. **Add to Home Screen** (iOS Safari: Share → Add to Home Screen). This is
   required for push notifications on iOS.

## What you get

- **Chat** over the WebSocket, with persisted history on reload.
- **Quick Capture** — jot a thought into memory; also wired as an OS share
  target (share text from any app → Animus).
- **Voice input** — mic button using the browser speech API (best on Android
  Chrome; iOS Safari support is partial).
- **Push notifications** — enable from the Status tab. Proactive nudges from
  the engine are delivered to your phone (requires VAPID keys, generated
  automatically on first use, and the `push` extra:
  `pip install -e "packages/bootstrap/[push]"`).

## Security notes

- `auth_required = "auto"` (default) enforces the token only for non-local
  clients; `"always"` enforces it for every non-public route, including
  loopback; `"never"` disables it.
- The PWA shell and static assets are public so the login page can load.
  Dashboard data, APIs, WebSocket, and other non-public routes require the
  bearer token when auth is enabled.
- The config file is stored `chmod 600` — it holds the token and VAPID private
  key.
- Tailscale ACLs remain your first line of defense: only enroll devices you
  trust.
