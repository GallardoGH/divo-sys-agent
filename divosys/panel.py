"""The ZERO EVO control panel in its own window: native WebView2, with browser app-mode as fallback.

The daemon owns the speaker; this module only shows the panel. Closing the window leaves the
service running (it is what keeps the Bluetooth link alive). Standard library only at import:
pywebview is used when present and every fallback keeps the panel reachable.
"""
import os
import subprocess
import webbrowser

from .config import DATA_DIR, HOST, PORT

TITLE = "ZERO EVO \u00b7 Panel"
WIDTH, HEIGHT = 1280, 860


def _url():
    return f"http://{HOST}:{PORT}/"


def _taskbar_identity():
    """Own the taskbar entry: group under our AppUserModelID and use the app's own icon.

    Without this, a pywebview window launched through the pythonw stub shows the generic Python
    icon and can group with unrelated Python windows. The icon comes from divo-sys.exe itself
    when the code runs packed, else from a generated .ico in the data folder."""
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ZERO.EVO.Panel")
    except Exception:
        pass
    from . import launch
    if launch.packed():
        exe = launch.archive_path()
        if exe:
            return str(exe)
    try:
        from . import icon
        return str(icon.write_icon(DATA_DIR / "panel.ico"))
    except Exception:
        return None


def _native():
    """A real window through pywebview (WebView2 runtime, present on every Windows 10/11).

    private_mode=False keeps the panel theme in localStorage under our data folder, so the
    window remembers itself between opens. Returns True if the window ran to close."""
    if os.name != "nt":
        return False
    try:
        import webview  # optional by design: the fallbacks below cover machines without it
    except Exception:
        return False
    try:
        storage = DATA_DIR / "webview"
        storage.mkdir(parents=True, exist_ok=True)
        webview.create_window(TITLE, _url(), width=WIDTH, height=HEIGHT, min_size=(900, 600), text_select=True)
        webview.start(storage_path=str(storage), private_mode=False, icon=_taskbar_identity())
        return True
    except Exception:
        return False


def _app_mode():
    """Fallback: Edge/Chrome --app. A dedicated window with its own taskbar entry, no browser chrome."""
    candidates = (
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
    )
    for exe in candidates:
        if exe and os.path.isfile(exe):
            subprocess.Popen([exe, f"--app={_url()}", f"--window-size={WIDTH},{HEIGHT}",
                              "--window-position=80,60"],
                             creationflags=0x00000008 if os.name == "nt" else 0)  # detached from our console
            return True
    return False


def open_panel():
    """Show the panel: native window first, then browser app-mode, then the default browser."""
    if _native():
        return True
    if _app_mode():
        return True
    return bool(webbrowser.open(_url()))
