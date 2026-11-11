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
- **Bearer token** on the `/api/*` surface and the chat WebSocket, so access
  isn't purely network-trust.

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

### Recommended: Tailscale Serve to the loopback-only dashboard

```bash
# Keep Animus private on the host and publish it only to the tailnet.
tailscale serve --bg https / http://127.0.0.1:7700
```

Keep the dashboard bound to loopback and require the token even from loopback
proxy traffic:

```toml
# ~/.config/animus/config.toml
[services]
host = "127.0.0.1"
auth_required = "always"
```

`"always"` is essential for this topology: Tailscale Serve and SSH tunnels
connect to the upstream from loopback. `"auto"` intentionally trusts loopback
and therefore cannot distinguish those proxies from an on-box browser.

Restart the dashboard. On first run with `auth_required` active it generates a
token in the chmod-600 config file. The full token is never logged. Retrieve it
directly from the protected config on Stheno and paste it into the PWA; do not
copy it through chat or shell-history-bearing commands.

To rotate it, clear `services.auth_token` in the protected config and restart.

Direct TLS termination in Uvicorn remains available for environments that need
it, but binding `0.0.0.0` widens the network surface and requires an independently
verified firewall/ACL policy. It is not the default personal-Stheno topology.

## 3. Build and serve the PWA

```bash
cd packages/pwa
npm install
npm run build      # outputs dist/
```

Serve `dist/` from the same origin as the dashboard (so `/api` and `/ws` are
same-origin). The static host must do **SPA fallback** (serve `index.html` for
unknown routes). Any static server behind the same Tailscale HTTPS name works.

## 4. Install on your phone

1. On your phone (with Tailscale connected), open
   `https://mybox.tailnet-name.ts.net`.
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

- `auth_required = "auto"` (default) enforces the token only when bound to a
  non-local host; `"always"` enforces it for loopback, proxied, and remote
  requests; `"never"` disables it.
- With auth active, every non-public dashboard/API route is token-gated. The
  public allowlist is limited to the PWA shell/static assets and bare liveness
  probe.
- The config file is stored `chmod 600` — it holds the token and VAPID private
  key.
- Tailscale ACLs remain your first line of defense: only enroll devices you
  trust.
- The current browser client stores the bearer token in Web Storage and passes
  it in the WebSocket handshake URL. Treat XSS, browser extensions, URL logging,
  and exported browser profiles as token-compromise paths; rotate after any
  suspected exposure. A short-lived WebSocket ticket is a future hardening item.
