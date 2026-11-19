"""MCP server (stdio, hand-rolled JSON-RPC, no SDK) that lets Claude use the Divoom Timebox Evo.

Every tool goes through the daemon, which enforces the permissions the user sets in the GUI.
A denied call is reported back as plain text so Claude can adapt instead of retrying.
"""
import json
import sys

from . import __version__, faces
from .client import get, send

MOOD_HELP = {
    "idle": "calm, blinking: nothing happening",
    "thinking": "eyes up, dots appearing: reasoning or planning",
    "working": "eyes scanning, progress bar: running tools, editing, building",
    "done": "happy with sparkles: finished successfully",
    "attention": "hopping, waving arms, wide eyes, yellow sparkles: I need the user (question, permission)",
    "error": "X eyes: something failed",
    "sleep": "dim, eyes shut, floating z: session over or idle",
    "splash": "the Claude starburst logo",
    "party": "party hat, cheering arms and falling confetti: celebrate a win",
    "sweat": "worried, sweat drops: a long task is still running",
}
COLOR = {"type": "string", "description": "hex colour like #FF6018"}

TOOLS = [
    {"name": "set_face",
     "description": "Show one of Claude's pixel faces on the Divoom screen to signal what I'm doing. Moods: "
                    + "; ".join(f"{k} = {v}" for k, v in MOOD_HELP.items()),
     "inputSchema": {"type": "object", "required": ["mood"], "properties": {"mood": {"type": "string", "enum": faces.MOODS}}}},
    {"name": "show_text",
     "description": "Scroll a short message across the screen (A-Z 0-9 and . ! ? : - + / _ , % ' ( )). Loops until replaced.",
     "inputSchema": {"type": "object", "required": ["text"], "properties": {
         "text": {"type": "string"}, "color": COLOR, "speed": {"type": "integer", "minimum": 1, "maximum": 4}}}},
    {"name": "draw_pixels",
     "description": "Draw custom 16x16 pixel art. Each frame is exactly 16 strings of exactly 16 characters; each "
                    "character is a key in `palette` (character -> hex colour). Unmapped characters are off. Several "
                    "frames animate and loop. LEDs wash colours out, so use fully saturated colours.",
     "inputSchema": {"type": "object", "required": ["frames", "palette"], "properties": {
         "frames": {"type": "array", "minItems": 1, "maxItems": 12, "items": {
             "type": "array", "minItems": 16, "maxItems": 16, "items": {"type": "string"}}},
         "palette": {"type": "object", "additionalProperties": {"type": "string"}},
         "delay_ms": {"type": "integer", "description": "per-frame delay, default 300"}}}},
    {"name": "set_brightness", "description": "Set the screen brightness, 0-100.",
     "inputSchema": {"type": "object", "required": ["percent"], "properties": {"percent": {"type": "integer", "minimum": 0, "maximum": 100}}}},
    {"name": "set_mode",
     "description": "Switch the speaker to one of its own modes. mode=clock (style 0-5, color, flags time/weather/temp/calendar), "
                    "light (color, kind 0-4, brightness), effect (kind 0-15), visualizer (kind 0-10), cloud, "
                    "scoreboard (red, blue), weather (temp in C, weather clear|cloudy|thunderstorm|rain|snow|fog), "
                    "sysmon (live CPU/RAM bars), network (latency graph), storage (battery and disk bars), "
                    "monitors (up/down grid of the user's watched sites), synctime.",
     "inputSchema": {"type": "object", "required": ["mode"], "properties": {
         "mode": {"type": "string", "enum": ["clock", "light", "effect", "visualizer", "cloud", "scoreboard", "weather", "sysmon", "network", "storage", "monitors", "synctime"]},
         "style": {"type": "integer"}, "kind": {"type": "integer"}, "color": COLOR, "brightness": {"type": "integer"},
         "time": {"type": "boolean"}, "weather": {"type": "string"}, "temp": {"type": "integer"}, "calendar": {"type": "boolean"},
         "red": {"type": "integer"}, "blue": {"type": "integer"}}}},
    {"name": "timer",
     "description": "Run a countdown (shows MM over SS plus a progress bar, then waves when done) or a stopwatch on the screen.",
     "inputSchema": {"type": "object", "required": ["action"], "properties": {
         "action": {"type": "string", "enum": ["start", "pause", "resume", "stop"]},
         "kind": {"type": "string", "enum": ["countdown", "stopwatch"]},
         "seconds": {"type": "integer", "description": "countdown length, 1-86399"}, "label": {"type": "string"}}}},
    {"name": "divoom_status",
     "description": "What the user currently allows me to do on the Divoom, whether it is connected, and what it shows. "
                    "Call this once if a tool was denied.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def _hex(c):
    c = c.lstrip("#")
    if len(c) != 6:
        raise ValueError(f"bad colour {c!r}, want #RRGGBB")
    return [int(c[i:i + 2], 16) for i in (0, 2, 4)]


def build_request(name, a):
    if name == "set_face":
        return {"cmd": "face", "mood": a["mood"]}
    if name == "show_text":
        r = {"cmd": "text", "text": a["text"]}
        if a.get("color"):
            r["color"] = _hex(a["color"])
        if a.get("speed"):
            r["speed"] = a["speed"]
        return r
    if name == "draw_pixels":
        pal = {k: _hex(v) for k, v in a["palette"].items()}
        out = []
        for i, fr in enumerate(a["frames"]):
            if len(fr) != 16 or any(len(row) != 16 for row in fr):
                raise ValueError(f"frame {i} must be 16 rows of exactly 16 characters")
            out.append({"px": [pal.get(ch, [0, 0, 0]) for row in fr for ch in row], "delay": a.get("delay_ms", 300)})
        return {"cmd": "frames", "frames": out}
    if name == "set_brightness":
        return {"cmd": "brightness", "value": a["percent"]}
    if name == "timer":
        return {"cmd": "timer", **{k: v for k, v in a.items() if v is not None}}
    if name == "set_mode":
        mode = a["mode"]
        if mode == "weather":
            return {"cmd": "weather", "temp": a.get("temp", 20), "weather": a.get("weather", "clear")}
        if mode == "synctime":
            return {"cmd": "synctime"}
        if mode in ("sysmon", "network", "storage", "monitors"):
            return {"cmd": "app", "name": "net" if mode == "network" else mode, "action": "start"}
        r = {"cmd": "mode", **{k: v for k, v in a.items() if v is not None}}
        if "color" in r:
            r["color"] = _hex(r["color"])
        return r
    raise ValueError(f"unknown tool {name}")


def call_tool(name, a):
    if name == "divoom_status":
        info = get("/api/claude")
        p = info["permissions"]
        allowed = [t for t, on in p["tools"].items() if on] if p["enabled"] else []
        off = [m for m, on in p["moods"].items() if not on]
        return json.dumps({"connected": info["connected"], "showing": info["showing"], "pinned_by_user": info["pinned"],
                           "claude_control_enabled": p["enabled"], "tools_allowed": allowed, "faces_disabled": off,
                           "auto_status_hooks": p["hooks"], "min_seconds_between_changes": p["min_interval_s"],
                           "brightness_range": [p["brightness_min"], p["brightness_max"]],
                           "quiet_hours": p["quiet_hours"]})
    r = send(build_request(name, a), "mcp")
    if r.get("denied"):
        return f"denied by the user's settings: {r['denied']}. Do not retry; call divoom_status to see what is allowed."
    if not r.get("ok"):
        raise ValueError(r.get("error", "daemon error"))
    return "ok" + ("" if r.get("connected") else " (speaker not connected yet; it will show when it is)")


def _reply(id_, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": id_}
    msg.update({"error": error} if error else {"result": result})
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if not isinstance(m, dict):
            continue
        method, id_ = m.get("method"), m.get("id")
        if id_ is None:
            continue  # notification
        if method == "initialize":
            _reply(id_, {"protocolVersion": (m.get("params") or {}).get("protocolVersion", "2024-11-05"),
                         "capabilities": {"tools": {}}, "serverInfo": {"name": "divo-sys", "version": __version__}})
        elif method == "tools/list":
            _reply(id_, {"tools": TOOLS})
        elif method == "tools/call":
            p = m.get("params") or {}
            try:
                _reply(id_, {"content": [{"type": "text", "text": call_tool(p.get("name"), p.get("arguments") or {})}]})
            except Exception as e:
                _reply(id_, {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True})
        elif method == "ping":
            _reply(id_, {})
        else:
            _reply(id_, error={"code": -32601, "message": f"method not found: {method}"})
