# Setup and troubleshooting

## Requirements

- Windows 10 or 11.
- Python 3.9 or newer **on your PATH**, from python.org (tick "Add python.exe to PATH") or the Microsoft Store. Nothing
  else to install. `divo-sys.exe` is the program in one file, but it still runs on your Python.
- A Divoom Timebox Evo, paired in **Windows Settings, Bluetooth and devices**. It shows up as `TimeBox-Evo-audio`.
  Pairing it for audio is all that is needed: the screen is controlled over a serial channel on the same link.
- Optional: [Claude Code](https://claude.com/claude-code) (for the hooks and MCP server), and the
  [GitHub CLI](https://cli.github.com/) signed in (for the build dot after a push).

The speaker accepts **one controller at a time**. Close the Divoom phone app while divo-sys is connected.

## The installer

Download `divo-sys-setup.exe` from the [latest release](https://github.com/haithamexe/divo-sys/releases/latest) and
double-click it. It asks whether to install (or update, if divo-sys is already there), then does everything in
"Automatic setup" below and opens the panel. Nothing is asked after that. To check the download, compare its SHA-256 with
the `.sha256` file on the release page.

It is not code-signed, so SmartScreen may show "Windows protected your PC". Choose **More info, Run anyway**.

How it finds Python: the file asks Windows to look up `pythonw.exe` on your PATH, so one download works on any PC. When
it installs itself it writes a copy that names the exact Python it found, so the installed app does not depend on PATH
afterwards. If you ever move or upgrade Python, run the setup file again (it offers to update).

To update later, download the newer `divo-sys-setup.exe` and run it: it offers to update, keeps your settings, and
replaces the app. To remove it, see "Running in the background" below.

You can also build the installer yourself: `python divo.py build-installer` writes `dist/divo-sys-setup.exe`.

## Setup from source

The installer and this section do the same thing. From a clone:

```
git clone https://github.com/haithamexe/divo-sys.git
cd divo-sys
python divo.py setup
```

What setup does, in order. Each step is safe to repeat.

1. **Installs the app.** Builds one `divo-sys.exe`, the whole program in a single file with its own name and icon, in
   `%LOCALAPPDATA%\Programs\divo-sys\` (no administrator rights needed), lists it under **Settings, Apps, Installed
   apps** so it can be removed like any other app, and brings your settings across from a checkout's `data/` folder.
2. Starts the background service.
3. Finds your speaker among the paired Bluetooth devices and saves its address. If you have more than one Divoom
   speaker it lists them and you pick one in the panel (**Settings, Find my speaker**).
4. Turns on **Start with Windows** (one entry under `HKCU\...\Run`, which Windows lists as **divo-sys**).
5. Adds the hooks to `~/.claude/settings.json`. Everything already there is kept, your original is saved once as
   `settings.json.bak-before-divo-sys`, and a file that is not valid JSON is never overwritten.
6. Registers the MCP server with `claude mcp add --scope user divo-sys`.
7. Puts a **divo-sys** icon on your desktop. It runs without a console window, starts the service if it is not
   running, and opens the panel. Add it to the Start menu too with `python divo.py shortcut startmenu`, or from
   **Settings** in the panel.

Options: `--no-app` (keep running from the checkout's scripts), `--no-hooks`, `--no-mcp`, `--no-autostart`,
`--no-shortcut`. Restart Claude Code afterwards.

### Why an app and not a script

Windows names a startup entry after the program it runs, so `pythonw.exe divo.py` shows up as **Python**, next to every
other Python and Node thing on the PC. The installed `divo-sys.exe` carries its own name, publisher and icon, so
Startup apps and Installed apps show **divo-sys**. The program lives inside that one file, so there are no loose
`.py` files to keep track of, and the data (settings, token, log) lives separately in `%LOCALAPPDATA%\divo-sys`, so
reinstalling or updating never touches your choices.

It is built from what Windows and Python already ship: pip's small windowless launcher stub, stamped with divo-sys's
icon and version information, with the program appended as a zip. It still needs Python installed, since it runs the
zip with a Python. `setup` builds it on your machine; the release's `divo-sys-setup.exe` is the same file built on a
clean Windows runner, and it is not code-signed. If you upgrade or move Python, run the setup file (or
`python divo.py setup`) again.

Open the panel with `python divo.py gui` (http://127.0.0.1:47831/). Nothing needs starting by hand: the service
starts at sign-in, and the first hook event or MCP call starts it if it is not running.

## Running in the background

The service has no window and no tray icon. It runs as `divo-sys.exe` plus a `pythonw.exe` helper (visible in Task
Manager, under Details), starts when you sign in to Windows, and reconnects to the speaker by itself. To change something later,
double-click the desktop icon (or open http://127.0.0.1:47831/). Closing the browser tab does not stop anything.

If Windows ever stops it from starting, look under **Settings, Apps, Startup** for **divo-sys** and make sure it is
on. Stop the service for good with **Settings, Stop service** in the panel, or `python divo.py stop`.

To remove everything: **Settings, Apps, Installed apps, divo-sys, Uninstall**, or `python divo.py uninstall` (removes the app,
the hooks, the MCP registration, the startup entry and the shortcuts, and stops the service). Your settings stay in
`%LOCALAPPDATA%\divo-sys`.

## Manual setup

**Speaker address.** `python divo.py discover` prints it. Or find it in Device Manager, the speaker's Bluetooth
properties, Details, "Bluetooth address". Enter it under **Settings** in the panel.

**MCP server:**

```
claude mcp add --scope user divo-sys -- python C:\path\to\divo-sys\divo.py mcp
```

**Hooks.** Add this to `~/.claude/settings.json` for each of `SessionStart`, `UserPromptSubmit`, `PreToolUse`,
`PostToolUse`, `PostToolUseFailure`, `Notification`, `SubagentStart`, `SubagentStop`, `Stop` and `SessionEnd`. The tool
events also take `"matcher": "*"`. `async` keeps the hook from ever slowing Claude down.

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [ { "type": "command", "command": "python C:/path/to/divo-sys/divo.py hook", "timeout": 10, "async": true } ] }
    ]
  }
}
```

**Start with Windows:** switch it on under **Settings** in the panel.

## Try it without a speaker

```
python divo.py demo
```

Runs a separate copy on http://127.0.0.1:47833/ with a pretend speaker, sample sessions and its own temporary
settings. Press Ctrl+C to close it. Nothing is written to your real settings.

## Troubleshooting

**"Not connected" in the panel.**
- Is the speaker on, in range, and not connected to the Divoom phone app?
- Is the address right? Press **Find my speaker** in Settings, then **Reconnect**.
- The panel shows the exact error. `%LOCALAPPDATA%\divo-sys`\daemon.log has more.
- If you have just paired it, Windows can take a minute to finish.

**Double-clicking the installer does nothing.** It could not find Python. Open a new Command Prompt and run
`pythonw --version`. If that fails, reinstall Python from python.org with "Add python.exe to PATH" ticked, or install
from source (`python divo.py setup`).

**Nothing changes when Claude works.**
- Did you restart Claude Code after `setup`? Hooks are read at start.
- Check the **Claude** page: is Claude control on, hooks on, and is the display pinned?
- A face you or Claude's tools picked holds for 30 seconds, and a speaker mode such as the clock holds until you press
  **Resume live status** (the Dashboard shows a banner when this is the reason).
- `python divo.py status` shows what the service thinks is going on.

**"Address already in use" or two copies running.** The port (47831) is the lock, so a second copy exits quietly. To
use another port set `DIVO_PORT` for every divo-sys command and the service.

**The picture is garbled right after a brightness change.** Known speaker quirk. The service waits half a second
after changing brightness for this reason; if you see it anyway, send the picture again.

**Antivirus asks about `pythonw.exe` or `divo-sys.exe` at startup.** The service runs without a window: `divo-sys.exe`
starts the `pythonw.exe` you installed and runs the program inside itself (`divo-sys.exe daemon`). Neither file is
code-signed, so a strict antivirus may ask once; the source is in this repository and the release has a checksum.

**Linux.** Pair the speaker with `bluetoothctl`, then enter its address in Settings or set it in
`data/settings.json`. The Windows-only parts (start with Windows, speaker discovery, battery) are skipped.

## What is remembered across restarts

Remembered (saved in `%LOCALAPPDATA%\divo-sys`\settings.json the moment you change it): every switch, number and list in the panel,
including the Claude permissions, Live status options, monitors, weather city, reminders, night mode, the speaker
address, Start with Windows, and the **Pin** switch.

Not remembered, by design, because they describe what is happening right now: a running timer or meter, the rotation,
a clock or effect you put on screen, and the "resume live status" hold. After a restart the screen goes back to live
status.

There is only ever one service: the port is the lock, and a second copy exits at once. If settings ever seem to
revert, check that exactly one `divo-sys.exe` process is running.

## Where things live

| Path | What |
| --- | --- |
| `%LOCALAPPDATA%\divo-sys`\settings.json | Your settings |
| `%LOCALAPPDATA%\divo-sys`\.token | The panel's per-run admin token |
| `%LOCALAPPDATA%\divo-sys`\daemon.log | The service's log |
| `%LOCALAPPDATA%\Programs\divo-sys\divo-sys.exe` | The installed app |
| `~/.claude/settings.json` | Where the hooks go. Set `CLAUDE_CONFIG_DIR` to use another folder |
