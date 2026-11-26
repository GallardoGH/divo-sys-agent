# Changelog

> Versiones X-agentN = este fork. Lo no listado aqui pertenece al historial de divo-sys (arriba).

## 0.3.0-agent1 (2026-11-22)

- Faces: 17 moods propios (zerofaces.py: ojos 6x5, pupila 2x2 por color de estado, boca/cejas/guiño/corazones). Anulables borrando el bloque final de faces.py.
- Night light (nightlight): lampara calida con franja/always, color, brillo, fundido; pausa caras; CLI divo nightlight on|off|enable|disable; tarjeta en panel. Default OFF.
- CLI: bright <0-100>; face <mood> valida y lista moods.
- Panel: UI en espanol integrada (original como index.html.en).
- Test design adaptados al nuevo diseno (175 OK, stdlib puro).

## Unreleased

- **Identidad OpenClaw (26-11)**: bloque de permisos `settings["agent"]` (migra desde el antiguo `"claude"` al leer), `/api/agent` con alias `/api/claude`, textos del panel (es + en) y del MCP/descripciones referidos a "el agente". Claude Code queda solo como forma de los payloads de hook y como via opcional `setup --hooks`; la integracion de referencia es OpenClaw.
- **Panel en ventana propia (26-11)**: `divo.py gui` abre una ventana nativa WebView2 via `divosys/panel.py` (pywebview opcional, tema guardado en `LOCALAPPDATA/divo-sys/webview`); fallback Edge/Chrome `--app`, ultimo recurso navegador por defecto. Cerrar la ventana NO para el daemon. Tests nuevos en `tests/test_panel.py`.

- **The attention face no longer flashes white.** It now hops with its arms waving and yellow sparkles around it, so it still
  catches the eye without a blinding frame. The "Flash if Claude has waited on you"
  setting is gone.
- **A "Test results" switch** (Live status page) turns off the pass-count screen shown after Claude runs your tests,
  without turning off the confetti and the glitch. With it off, a passing run shows confetti and a failing one the glitch.

## 0.3.0

- **A real Windows app.** `divo-sys.exe` is one file with its own name, icon and version information, so Startup apps
  and Installed apps list **divo-sys** instead of "Python". The program lives inside the file; settings live
  separately in `%LOCALAPPDATA%\divo-sys`.
- **`divo-sys-setup.exe`**, a download on each release. Double-click it: it installs the app, finds your speaker, starts
  with Windows, adds the Claude Code hooks, the MCP server and a desktop icon, and opens the panel. A newer setup file
  updates an existing install and keeps your settings. It needs Python 3.9+ on PATH and is not code-signed; each
  release carries a `.sha256` file.
- The release workflow builds the installer on a clean Windows runner and attaches it with its checksum.
- Installed from the app, Uninstall appears under **Settings, Apps, Installed apps**.

## 0.2.0

- **Fixed settings being lost after a restart on Windows.** The "one service per machine" lock did not hold, so several
  copies ran and stale ones overwrote saved settings. The service now binds exclusively and a second copy exits at once.
- Saving another setting no longer touches the Windows startup entry. The **Pin** switch is saved.
- A desktop icon that opens the panel (and starts the service if needed).
- Docs for running in the background.

## 0.1.0

First public release.

- Live status from Claude Code hooks: thinking, working with a picture of the tool, waiting, done, failed, one face per
  session or a board when several are open; heartbeat, sub-agent dots, build dot, test results, confetti, glitch.
- A permission layer you control: master switch, per-tool and per-face switches, rate limits, quiet hours, Pin.
- Timers, CPU/RAM, network, battery and disk meters, site monitors, weather, reminders, night dimming, and the speaker's
  own clock, light, effects, visualizer and scoreboard.
- One-command `setup` and `uninstall`, speaker discovery, a no-hardware `demo` mode.
- Python standard library only; no cloud, no account.
