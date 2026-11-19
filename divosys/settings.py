"""Persistent settings (data/settings.json). Unknown keys are dropped, wrong types are ignored."""
import copy
import json
import os
import threading
from pathlib import Path

from . import faces

from .config import DATA_DIR, LEGACY_DATA_DIR, ROOT  # noqa: F401

TOOLS = ["set_face", "show_text", "draw_pixels", "set_brightness", "set_mode", "timer"]


def defaults():
    return {
        "device": {"address": "", "channel": 1},
        "brightness": 100,
        "idle_sleep_minutes": 10,
        "sync_time_on_connect": True,
        "autostart": False,
        "pinned": False,  # the Pin switch survives a restart
        # What Claude (the MCP tools and the status hooks) is allowed to do.
        "claude": {
            "enabled": True,
            "hooks": True,
            "tools": {t: True for t in TOOLS},
            "moods": {m: True for m in faces.MOODS},
            "override_pin": False,
            "min_interval_s": 1.0,
            "brightness_min": 20,
            "brightness_max": 100,
            "max_text_chars": 28,
            "quiet_hours": {"enabled": False, "start": "23:00", "end": "07:00"},
        },
        # Claude's live status on the speaker (driven by Claude Code hooks).
        "scene": {"mode": "auto", "glyphs": True, "heartbeat": True, "agent_dots": True, "ci_dot": True,
                  "reactions": True, "test_results": True, "elapsed_clock": False,
                  "tool_pictures": {k: True for k in faces.GLYPH_KINDS}, "sweat_after_s": 180, "hold_seconds": 30},
        "monitors": {"items": [], "alert": True, "interval_s": 30},
        "weather": {"enabled": False, "city": "", "lat": 0.0, "lon": 0.0},
        "night": {"enabled": False, "start": "22:00", "end": "07:00", "brightness": 15},
        "reminders": [],
        "rotation": {"items": [
            {"type": "face", "mood": "idle", "seconds": 10},
            {"type": "face", "mood": "splash", "seconds": 6},
            {"type": "app", "name": "sysmon", "seconds": 10},
        ]},
    }


def _merge(base, over):
    """Overlay `over` on `base`, keeping base's shape and types."""
    out = copy.deepcopy(base)
    if not isinstance(over, dict):
        return out
    for k, bv in base.items():
        if k not in over:
            continue
        ov = over[k]
        if isinstance(bv, dict):
            out[k] = _merge(bv, ov)
        elif isinstance(bv, bool):
            if isinstance(ov, bool):
                out[k] = ov
        elif isinstance(bv, (int, float)):
            # finite and modest: infinity, NaN and huge values crash timers and sleeps deep inside the threads
            if isinstance(ov, (int, float)) and not isinstance(ov, bool) and abs(ov) <= 1e6:
                out[k] = ov
        elif isinstance(bv, str):
            if isinstance(ov, str):
                out[k] = ov
        elif isinstance(bv, list):
            if isinstance(ov, list):
                out[k] = ov
    return out


class Settings:
    def __init__(self, path=None):
        self.path = Path(path) if path else DATA_DIR / "settings.json"
        self.lock = threading.RLock()
        self.data = defaults()
        sources = [self.path]
        if not path and not os.environ.get("DIVO_DATA"):
            sources.append(LEGACY_DATA_DIR / "settings.json")  # first run after the data folder moved
        for source in sources:
            try:
                self.data = _merge(defaults(), json.loads(source.read_text(encoding="utf-8")))
                break
            except (OSError, ValueError):
                continue

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def patch(self, over):
        with self.lock:
            self.data = _merge(self.data, over)
            self.save()
            return copy.deepcopy(self.data)

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # owner only on Linux/macOS
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(self.data, indent=2))
            os.replace(tmp, self.path)
