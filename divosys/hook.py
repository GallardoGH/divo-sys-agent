"""Agent hook: forward a lifecycle event (Claude-Code-shaped payloads, also reusable by other harnesses) to the daemon. Never blocks, never fails.

Registered for several events; the harness sends the event as JSON on stdin. `divo.py hook <mood>` is kept
as a fallback that just shows a face.
"""
import json
import sys
import time

from . import toolinfo


def build(data, fallback_mood=None):
    """Turn a hook payload into a request for the daemon."""
    ev = str(data.get("hook_event_name") or "")
    if not ev:
        return {"cmd": "face", "mood": fallback_mood or "idle"}
    req = {"cmd": "event", "event": ev, "session": str(data.get("session_id") or ""), "cwd": str(data.get("cwd") or ""),
           "ts": time.time()}
    if ev in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
        tool = data.get("tool_name")
        inp = data.get("tool_input")
        command = str(inp.get("command") or "") if isinstance(inp, dict) else ""
        req["tool"] = tool
        req["kind"] = toolinfo.tool_kind(tool, command)
        if tool == "Bash" and ev != "PreToolUse":
            if ev == "PostToolUse":
                resp = data.get("tool_response")
                text = (str(resp.get("stdout") or "") + str(resp.get("stderr") or "")) if isinstance(resp, dict) else str(resp or "")
                if toolinfo.is_push(command):
                    req["push"] = True
            else:
                text = str(data.get("error") or "")
            if req["kind"] == "test":
                tests = toolinfo.parse_test_output(text)
                req["tests"] = list(tests) if tests else None
    elif ev == "Notification":
        req["ntype"] = data.get("notification_type")
    return req


def run(fallback_mood=None):
    try:
        if sys.stdin is None or sys.stdin.isatty():
            raw = ""
        elif hasattr(sys.stdin, "buffer"):
            raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        else:
            raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        from .client import send
        send(build(data if isinstance(data, dict) else {}, fallback_mood), "hook")
    except Exception:
        pass
    sys.exit(0)
