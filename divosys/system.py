"""Machine readings (CPU, memory, battery, disk) and start-with-Windows, standard library only.

The Windows parts use ctypes and winreg and are only loaded on Windows, so the rest of the project still imports
and runs its tests on Linux and macOS (where the readings fall back to simple approximations).
"""
import os
import shutil
import sys

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "divo-sys"
_last_cpu = None

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class _FileTime(ctypes.Structure):
        _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]

        def value(self):
            return (self.hi << 32) | self.lo

    class _MemStatus(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD), ("total_phys", ctypes.c_ulonglong),
                    ("avail_phys", ctypes.c_ulonglong), ("total_page", ctypes.c_ulonglong),
                    ("avail_page", ctypes.c_ulonglong), ("total_virt", ctypes.c_ulonglong),
                    ("avail_virt", ctypes.c_ulonglong), ("avail_ext", ctypes.c_ulonglong)]

    class _PowerStatus(ctypes.Structure):
        _fields_ = [("ac", ctypes.c_ubyte), ("flag", ctypes.c_ubyte), ("percent", ctypes.c_ubyte),
                    ("saver", ctypes.c_ubyte), ("life", wintypes.DWORD), ("full", wintypes.DWORD)]


def cpu_percent():
    """CPU use since the previous call (Windows); a load-average estimate elsewhere."""
    global _last_cpu
    if os.name != "nt":
        try:
            return max(0.0, min(100.0, 100.0 * os.getloadavg()[0] / (os.cpu_count() or 1)))
        except (AttributeError, OSError):
            return 0.0
    idle, kernel, user = _FileTime(), _FileTime(), _FileTime()
    ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
    now = (idle.value(), kernel.value(), user.value())
    prev, _last_cpu = _last_cpu or (0, 0, 0), now
    d_idle, d_kernel, d_user = (now[i] - prev[i] for i in range(3))
    total = d_kernel + d_user  # kernel time already includes idle time
    return 0.0 if total <= 0 else max(0.0, min(100.0, 100.0 * (1 - d_idle / total)))


def mem_percent():
    if os.name == "nt":
        m = _MemStatus()
        m.length = ctypes.sizeof(m)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return float(m.load)
    try:  # Linux
        info = {}
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                key, _, rest = line.partition(":")
                info[key] = int(rest.split()[0])
        return 100.0 * (1 - info["MemAvailable"] / info["MemTotal"])
    except (OSError, KeyError, ValueError, IndexError, ZeroDivisionError):
        return 0.0


def battery():
    """(percent or None when there is no battery, charging)."""
    if os.name != "nt":
        return None, False
    st = _PowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):
        return None, False
    if st.flag == 128 or st.percent == 255:  # no system battery / unknown
        return None, False
    return float(st.percent), st.ac == 1


def disk_used_percent(path=None):
    if path is None:
        path = (os.environ.get("SystemDrive", "C:") + "\\") if os.name == "nt" else "/"
    u = shutil.disk_usage(path)
    return 100.0 * u.used / u.total


def _daemon_command():
    from . import launch
    return launch.quote(launch.service_command())


def autostart_enabled():
    if os.name != "nt":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, _RUN_NAME)
            return True
    except OSError:
        return False


def set_autostart(on):
    if os.name != "nt":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, _RUN_NAME, 0, winreg.REG_SZ, _daemon_command())
        else:
            try:
                winreg.DeleteValue(k, _RUN_NAME)
            except OSError:
                pass
