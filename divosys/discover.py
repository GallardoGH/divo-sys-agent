"""Find a paired Divoom speaker without asking the user for its Bluetooth address.

Windows lists paired Bluetooth devices as PnP devices whose instance id contains the 12-digit address
(`BTHLE\\DEV_0123456789AB\\...`). We ask PowerShell (part of Windows) for devices whose name looks like a Divoom
speaker and pull the address out of the id. Nothing is sent anywhere.
"""
import os
import re
import subprocess

NAME_PATTERN = r"time\s?box|divoom|ditoo|pixoo|tivoo|voombox"
_ADDR = re.compile(r"DEV_([0-9A-Fa-f]{12})")
_SUFFIX = re.compile(r"[-_ ](audio|light|le)$", re.I)


def parse_devices(text):
    """Turn lines of 'Friendly Name|InstanceId' into [{name, address}], one entry per address."""
    seen, out = set(), []
    for line in (text or "").splitlines():
        name, _, instance = line.partition("|")
        m = _ADDR.search(instance)
        if not m:
            continue
        raw = m.group(1).upper()
        address = ":".join(raw[i:i + 2] for i in range(0, 12, 2))
        if address in seen:
            continue
        seen.add(address)
        out.append({"name": _SUFFIX.sub("", name.strip()) or "Divoom speaker", "address": address})
    return out


def find_speakers(timeout=25):
    """Paired devices that look like a Divoom speaker. Empty on other systems or when none is paired."""
    if os.name != "nt":
        return []
    script = ("Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object { $_.FriendlyName -match '" + NAME_PATTERN
              + "' } | ForEach-Object { $_.FriendlyName + '|' + $_.InstanceId }")
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                              capture_output=True, text=True, timeout=timeout, creationflags=0x08000000)
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_devices(done.stdout)
