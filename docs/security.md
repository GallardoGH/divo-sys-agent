# Security and privacy

divo-sys runs a small web server on your machine and takes input from Claude Code hooks, an MCP server and the web
panel. This page says what is protected, what is not, and what it contacts.

## What it contacts

Nothing, unless you set it up:

| Feature | Contacts | Sends |
| --- | --- | --- |
| Monitors | The sites you list | A GET request every 30 seconds (configurable) |
| Build dot | GitHub, through your own `gh` login | Only after a `git push`: which commit's run to look up |
| Weather | `api.open-meteo.com` (and `geocoding-api.open-meteo.com` while you search for a city) | The coordinates of the city you picked. No account |
| Network graph | `1.1.1.1:443` | A TCP connect, only while the graph is running |

No analytics, no telemetry, no update checks.

## The local server

It binds to `127.0.0.1` only. Because any web page you open can send requests to localhost, every request is checked:

- **Host header** must be exactly `127.0.0.1:<port>` or `localhost:<port>` (defeats DNS rebinding).
- **Origin header**, if present, must be the panel's own origin.
- **A custom `X-Divo` header** is required. Browsers will not add it to a cross-site request without a CORS preflight,
  and the server never answers a preflight.
- **Anything that changes settings, pins the screen or acts as you** needs the per-run **admin token**, which only the
  served panel page holds.
- The page is sent with `X-Frame-Options: DENY`, a strict `Content-Security-Policy` (no framing, no connections
  elsewhere), `nosniff` and `no-referrer`. The panel builds its pages from text only, never from HTML strings.
- Request bodies are capped at 2 MB, must be JSON objects, and connections time out.

## What Claude can and cannot do

Claude's tools and the hooks run with the lowest privilege tier (`mcp` and `hook`). They can ask for faces, text,
drawings, brightness, modes and timers, subject to your switches. They **cannot** change settings, pin or unpin,
resume live status, stop the service or read the token through the API.

## Honest limits

This is a status light, not a security product. Please read these:

- **The permission switches are guardrails, not a sandbox.** The panel's token is in the page that `GET /` serves and
  in `%LOCALAPPDATA%\divo-sys`\.token, and `%LOCALAPPDATA%\divo-sys`\settings.json is a plain file. Any process running as your user, including a Claude
  session that can run shell commands, can read them. If you need a hard boundary, use Claude Code's own permission
  rules (for example deny `Bash(python *divo.py*)`) rather than relying on these switches.
- **Any local process can change the face.** The `mcp` and `hook` tiers need no password, by design, so that a hook
  costs nothing. They are still limited to what the switches allow.
- **`/api/state` is readable by any local process** and includes project folder names (not paths) and the activity log.
  It never includes site addresses, which can carry tokens.
- **Site checks tolerate an incomplete certificate chain.** Windows loads root certificates lazily, so Python can fail
  to verify a site a browser accepts. When the only problem is "cannot build the chain locally", the check retries
  without verification and reports the site as up with a note. An expired, wrong-host or self-signed certificate still
  counts as down. This only affects the up/down light, never what is sent.
- **Files are written with default permissions** on Windows (they inherit your folder's access). On Linux and macOS
  `%LOCALAPPDATA%\divo-sys`\.token and `settings.json` are created owner-only (mode 0600).

## Things deliberately refused

- A folder that is a network path (`\\host\share` or `//host/share`) is never handed to `git` or `gh`: touching one
  makes Windows open a connection to that machine.
- `git` is run with `core.fsmonitor` off, since a booby-trapped repository config can use it to run a program.
- Timestamps from hooks are never trusted beyond "now", numbers in settings must be finite and sane, and the number of
  tracked sessions is capped, so a misbehaving caller cannot freeze or exhaust the service.

## Reporting a problem

Please open a GitHub issue for anything that is not sensitive. For something that is, use GitHub's private
vulnerability reporting on the repository's Security tab.
