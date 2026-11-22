"""The brain: owns what the speaker shows, who may change it, and the Bluetooth link.

Everything that changes the display goes through Engine.handle(req, source). Requests are
coalesced into one "latest display" slot, because only the newest picture matters and
the speaker drops its connection if it is flooded.
"""
import collections
import copy
import datetime
import math
import os
import threading
import time

from . import discover, faces, monitors, policy, protocol, scene, system
from .settings import Settings


def _to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _rgb(c, default=(255, 96, 24)):
    try:
        r, g, b = (max(0, min(255, int(v))) for v in c)
        return (r, g, b)
    except (TypeError, ValueError):
        return default


class Engine:
    def __init__(self, settings=None, transport=protocol.Timebox, clock=time.time, threads=True):
        self.settings = settings or Settings()
        self.transport = transport
        self.clock = clock
        self.use_threads = threads
        self.cv = threading.Condition(threading.RLock())
        self.quit = threading.Event()
        self.reconnect_flag = False
        self.started = clock()
        self.nlight_active = False          # night light (fork ZERO) state
        self.nlight_until = 0.0
        self.nlight_fade_at = 0.0
        self.nlight_fade_step = 0

        self.pinned = bool(self.settings.snapshot().get("pinned", False))
        self.connected = False
        self.last_error = ""
        self.log = collections.deque(maxlen=300)
        self.current = {"kind": "none", "label": "Starting", "source": "system", "since": clock(), "mood": None}
        self.preview = {"id": 0, "frames": None, "color": None}
        self.out = {"version": 0, "packets": []}
        self.cmds = []           # one-shot packets (weather, time sync)
        self.restore_req = None  # request that produced the current display
        self.temp = None         # {"until", "restore"} while a reminder is flashing
        self.app = None          # running live app: {"name", "params", "state"}
        self.scoreboard = {"red": 0, "blue": 0}
        self.last_change = 0.0   # last time Claude changed something
        self.last_activity = clock()
        self.events = []         # one-shot notices for the GUI (timer finished...)
        self._fired = set()
        self._bright_sent = None
        self._last_discover = 0.0
        self._last_tick_error = None
        # Claude Code live status
        self.sessions = {}
        self.scene_active = False
        self.hold_until = 0.0     # a display set by you (or Claude's tools) keeps the live status away until then
        self.flash = None         # brief reaction (party, tests, glitch) drawn over the live status
        self.scene_dirty = False
        self.scene_last = 0.0
        self._scene_logged = None
        self.ci = None
        self.weather_state = None
        self.net_samples = collections.deque(maxlen=16)
        self._net_busy = False
        self.uptime = monitors.UptimeMonitor(self)
        self.ci_watch = monitors.CiWatcher(self)
        self.weather = monitors.WeatherPoller(self)

    # ---- logging ----------------------------------------------------------------------
    def _log(self, source, action, ok=True, detail=""):
        self.log.appendleft({"t": self.clock(), "source": source, "action": str(action)[:80], "ok": ok,
                             "detail": str(detail)[:200]})

    # ---- entry point ------------------------------------------------------------------
    def handle(self, req, source="mcp"):
        if not isinstance(req, dict) or "cmd" not in req:
            return {"ok": False, "error": "bad request"}
        with self.cv:
            if req.get("cmd") == "event":
                return self._handle_event(req, source)
            cfg = self.settings.snapshot()["claude"]
            ok, reason, req = policy.decide(cfg, req, source, self.pinned, datetime.datetime.now(),
                                            self.last_change, self.clock())
            if not ok:
                self._log(source, policy.describe(req), False, reason)
                return {"ok": False, "denied": reason, "connected": self.connected}
            try:
                self._apply(req, source)
            except (ValueError, KeyError, TypeError, OverflowError) as e:
                self._log(source, policy.describe(req), False, f"invalid: {e}")
                return {"ok": False, "error": str(e)}
            if source not in policy.PRIVILEGED:
                self.last_change = self.clock()
            if source != "system":
                self.last_activity = self.clock()
                self.temp = None
            return {"ok": True, "connected": self.connected}

    # ---- applying requests --------------------------------------------------------------
    def _apply(self, req, source):
        cmd = req["cmd"]
        if cmd == "face":
            mood = req["mood"]
            if mood not in faces.FACES:
                raise ValueError(f"unknown mood {mood!r}")
            self._show_frames(faces.FACES[mood], f"face · {mood}", "face", source, req, mood=mood)
        elif cmd == "text":
            text = str(req["text"]).strip()
            if not text:
                raise ValueError("empty text")
            color = _rgb(req.get("color"), faces.CORAL)
            step = max(1, min(4, int(req.get("speed", 2))))
            self._show_frames(faces.text_frames(text, color, step=step), f"text · {text[:24]}", "text", source, req)
        elif cmd == "frames":
            fr = req["frames"]
            if not 1 <= len(fr) <= 12:
                raise ValueError("1 to 12 frames")
            frames = []
            for f in fr:
                px = [_rgb(p, (0, 0, 0)) for p in f["px"]]
                if len(px) != 256:
                    raise ValueError("each frame needs 256 pixels")
                frames.append((px, max(50, min(5000, int(f.get("delay", 300))))))
            self._show_frames(frames, f"drawing · {len(frames)} frame(s)", "frames", source, req)
        elif cmd == "mode":
            self._set_mode(req, source)
        elif cmd == "brightness":
            self.settings.patch({"brightness": max(0, min(100, int(req["value"])))})
            self._log(source, f"brightness · {req['value']}%")
            self.cv.notify_all()
        elif cmd == "weather":
            self.cmds.append(protocol.weather_packet(int(req.get("temp", 20)), str(req.get("weather", "clear"))))
            self._log(source, f"weather · {req.get('temp')}° {req.get('weather', 'clear')}")
            self.cv.notify_all()
        elif cmd == "synctime":
            self.cmds.append(protocol.time_packet())
            self._log(source, "time synced to PC clock")
            self.cv.notify_all()
        elif cmd == "nightlight":
            self._nightlight_request(req, source)
        elif cmd == "pin":
            self.pinned = bool(req.get("value"))
            self.settings.patch({"pinned": self.pinned})
            self._log(source, "display pinned" if self.pinned else "display unpinned")
        elif cmd == "app":
            self._app_request(req, source)
        elif cmd == "timer":
            self._timer_request(req, source)
        elif cmd == "scene":
            self._scene_request(req, source)
        elif cmd == "status":
            pass
        else:
            raise ValueError(f"unknown command {cmd!r}")

    def _set_mode(self, req, source):
        mode = req["mode"]
        self._stop_app()
        if mode == "clock":
            style = max(0, min(5, int(req.get("style", 0))))
            color = _rgb(req.get("color"), (255, 255, 255))
            pk = protocol.clock_packet(style, color, bool(req.get("time", True)), bool(req.get("weather", False)),
                                       bool(req.get("temp", False)), bool(req.get("calendar", False)))
            self._show_packets([pk], f"clock · {protocol.CLOCK_STYLES[style]}", "mode", source, req)
        elif mode == "light":
            color = _rgb(req.get("color"), (255, 255, 255))
            kind = max(0, min(4, int(req.get("kind", 0))))
            pk = protocol.light_packet(color, int(req.get("brightness", 100)), kind, bool(req.get("power", True)))
            self._show_packets([pk], f"light · {protocol.LIGHT_TYPES[kind]}", "mode", source, req,
                               frames=[(faces.solid_frame(color), 1000)] if kind == 0 else None)
        elif mode == "effect":
            kind = max(0, min(len(protocol.EFFECTS) - 1, int(req.get("kind", 0))))
            self._show_packets([protocol.effect_packet(kind)], f"effect · {protocol.EFFECTS[kind]}", "mode", source, req)
        elif mode == "visualizer":
            kind = max(0, min(protocol.VISUALIZER_COUNT - 1, int(req.get("kind", 0))))
            self._show_packets([protocol.visualizer_packet(kind)], f"visualizer · {kind + 1}", "mode", source, req)
        elif mode == "cloud":
            self._show_packets([protocol.cloud_packet()], "cloud channel", "mode", source, req)
        elif mode == "scoreboard":
            r = max(0, min(999, int(req.get("red", 0))))
            b = max(0, min(999, int(req.get("blue", 0))))
            self.scoreboard = {"red": r, "blue": b}
            self._show_packets([protocol.scoreboard_packet(r, b)], f"scoreboard · {r} - {b}", "mode", source, req)
        else:
            raise ValueError(f"unknown mode {mode!r}")

    # ---- showing things -----------------------------------------------------------------
    def _show_frames(self, frames, label, kind, source, req, mood=None, quiet=False, keep_app=False, scene=False):
        self._show_packets(protocol.display_packets(frames), label, kind, source, req, frames=frames,
                           mood=mood, quiet=quiet, keep_app=keep_app, scene=scene)

    def _show_packets(self, packets, label, kind, source, req, frames=None, mood=None, quiet=False, keep_app=False,
                      scene=False):
        if not keep_app:
            self.app = None
        if scene:
            self.scene_active = True
            self.restore_req = None
        else:
            self.scene_active = False
            if source in ("gui", "mcp") and kind != "app":
                # what you (or Claude's tools) put on screen is not stomped by the automatic status right away
                self.hold_until = float("inf") if (source == "gui" and kind == "mode") else \
                    self.clock() + self.settings.snapshot()["scene"]["hold_seconds"]
        self.out = {"version": self.out["version"] + 1, "packets": packets}
        self.current = {"kind": kind, "label": label, "source": source, "since": self.clock(), "mood": mood}
        self.preview = {"id": self.preview["id"] + 1, "frames": frames}
        if not keep_app and req is not None:
            self.restore_req = req
        if not quiet:
            self._log(source, label)
        self.cv.notify_all()

    # ---- live apps ----------------------------------------------------------------------
    def _stop_app(self):
        self.app = None

    def _app_request(self, req, source):
        name, action = req.get("name"), req.get("action", "start")
        if name not in ("sysmon", "rotation", "net", "storage", "monitors"):
            raise ValueError(f"unknown app {name!r}")
        if action == "stop":
            if self.app and self.app["name"] == name:
                self.app = None
                self._log(source, f"{name} stopped")
            return
        self.app = {"name": name, "params": {}, "state": {"last": 0, "idx": -1}}
        self.restore_req = req
        self._log(source, f"{name} started")
        self._tick_app(self.clock(), first=True)

    def _timer_request(self, req, source):
        action = req.get("action", "start")
        now = self.clock()
        t = self.app if self.app and self.app["name"] == "timer" else None
        if action == "start":
            kind = req.get("kind", "countdown")
            if kind not in ("countdown", "stopwatch"):
                raise ValueError("kind must be countdown or stopwatch")
            secs = max(1, min(86399, int(req.get("seconds", 300))))
            self.app = {"name": "timer", "params": {"kind": kind, "total": secs, "label": str(req.get("label", ""))[:30]},
                        "state": {"start": now, "paused": None, "paused_total": 0.0, "last": -1}}
            self.restore_req = None
            self._log(source, f"{kind} started" + (f" · {secs // 60}m{secs % 60:02d}s" if kind == "countdown" else ""))
            self._tick_app(now, first=True)
        elif t is None:
            raise ValueError("no timer is running")
        elif action == "stop":
            self.app = None
            self._log(source, "timer stopped")
        elif action == "pause" and t["state"]["paused"] is None:
            t["state"]["paused"] = now
            self._log(source, "timer paused")
        elif action == "resume" and t["state"]["paused"] is not None:
            t["state"]["paused_total"] += now - t["state"]["paused"]
            t["state"]["paused"] = None
            self._log(source, "timer resumed")

    def timer_info(self):
        t = self.app
        if not t or t["name"] != "timer":
            return None
        s, p = t["state"], t["params"]
        elapsed = (s["paused"] or self.clock()) - s["start"] - s["paused_total"]
        remaining = max(0, p["total"] - elapsed) if p["kind"] == "countdown" else None
        return {"kind": p["kind"], "label": p["label"], "total": p["total"], "elapsed": elapsed,
                "remaining": remaining, "paused": s["paused"] is not None}

    def _tick_app(self, now, first=False):
        app = self.app
        if not app or (self.temp and not first):  # an alert is on screen: the app redraws after it
            return
        name, st = app["name"], app["state"]
        if name == "timer":
            info = self.timer_info()
            if info["kind"] == "countdown":
                if info["remaining"] <= 0:
                    label = info["label"] or "timer"
                    self.app = None
                    self.events.append({"type": "timer_done", "label": label, "t": now})
                    self._show_frames(faces.FACES["attention"], f"timer finished · {label}", "face", "system", None)
                    return
                secs = math.ceil(info["remaining"])
                frame = faces.timer_frame(secs, info["total"])
            else:
                secs = int(info["elapsed"])
                frame = faces.timer_frame(secs, None)
            if secs != st["last"]:
                st["last"] = secs
                self._show_frames([(frame, 1000)], f"timer · {secs}s", "app", "system", None, quiet=True, keep_app=True)
        elif name == "sysmon":
            if first or now - st["last"] >= 2:
                st["last"] = now
                st["cpu"], st["ram"] = system.cpu_percent(), system.mem_percent()
                self._show_frames([(faces.sysmon_frame(st["cpu"], st["ram"]), 1000)],
                                  f"system · CPU {st['cpu']:.0f}%  RAM {st['ram']:.0f}%", "app", "system", None,
                                  quiet=True, keep_app=True)
        elif name == "net":
            if first or now - st["last"] >= 2:
                st["last"] = now
                self._net_probe_async()
                last = next((x for x in reversed(self.net_samples) if x is not None), None)
                self._show_frames([(faces.net_frame(self.net_samples), 1000)],
                                  f"network · {last} ms" if last is not None else "network · probing", "app", "system",
                                  None, quiet=True, keep_app=True)
        elif name == "storage":
            if first or now - st["last"] >= 5:
                st["last"] = now
                batt, charging = system.battery()
                disk = system.disk_used_percent()
                self._show_frames([(faces.storage_frame(batt, charging, disk), 1000)],
                                  f"storage · disk {disk:.0f}% used" + (f" · battery {batt:.0f}%" if batt is not None else ""),
                                  "app", "system", None, quiet=True, keep_app=True)
        elif name == "monitors":
            if first or now - st["last"] >= 2:
                st["last"] = now
                states = self.uptime.states()
                up = sum(1 for x in states if x in ("up", "slow"))
                self._show_frames([(faces.monitor_frame(states, int(now) % 2 == 0), 1000)],
                                  f"sites · {up}/{len(states)} up" if states else "sites · none configured", "app",
                                  "system", None, quiet=True, keep_app=True)
        elif name == "rotation":
            items = [i for i in self.settings.snapshot()["rotation"]["items"] if isinstance(i, dict)]
            if not items:
                self.app = None
                return
            cur = items[st["idx"] % len(items)] if st["idx"] >= 0 else None
            hold = max(3, _to_int((cur or {}).get("seconds", 10), 10))
            if first or now - st["last"] >= hold:
                st["idx"] = (st["idx"] + 1) % len(items)
                st["last"] = now
                self._show_rotation_item(items[st["idx"]])

    def _show_rotation_item(self, item):
        kind = item.get("type")
        if kind == "face" and item.get("mood") in faces.FACES:
            self._show_frames(faces.FACES[item["mood"]], f"rotation · {item['mood']}", "app", "system", None,
                              quiet=True, keep_app=True)
        elif kind == "text" and str(item.get("text", "")).strip():
            self._show_frames(faces.text_frames(str(item["text"]), _rgb(item.get("color"), faces.CORAL)),
                              f"rotation · {str(item['text'])[:20]}", "app", "system", None, quiet=True, keep_app=True)
        elif kind == "app" and item.get("name") == "sysmon":
            cpu, ram = system.cpu_percent(), system.mem_percent()
            self._show_frames([(faces.sysmon_frame(cpu, ram), 1000)], "rotation · system", "app", "system", None,
                              quiet=True, keep_app=True)

    # ---- scheduled things ---------------------------------------------------------------
    def effective_brightness(self, now=None):
        s = self.settings.snapshot()
        b = int(s["brightness"])
        n = s["night"]
        if n["enabled"] and policy.in_window((now or datetime.datetime.now()).strftime("%H:%M"), n["start"], n["end"]):
            b = min(b, int(n["brightness"]))
        return b

    def tick(self, now_dt=None):
        """Called about 4 times a second."""
        now_dt = now_dt or datetime.datetime.now()
        now = self.clock()
        with self.cv:
            self._tick_app(now)
            if self.temp and now >= self.temp["until"]:
                restore, self.temp = self.temp["restore"], None
                if restore:
                    self._apply(restore, "system")
                elif self.app:
                    self._tick_app(now, first=True)  # redraw the running app straight away
                elif self.sessions:
                    self.scene_dirty, self.scene_active = True, False
                else:
                    self._apply({"cmd": "face", "mood": "idle"}, "system")
            self._check_reminders(now_dt, now)
            self._nightlight_tick(now_dt, now)
            self._scene_tick(now)
            minutes = self.settings.snapshot()["idle_sleep_minutes"]
            if (minutes > 0 and self.current["source"] in ("hook", "mcp") and self.current["kind"] != "scene"
                    and self.current.get("mood") != "sleep"
                    and not self.nlight_active
                    and not self.pinned and now - self.last_activity > minutes * 60):
                self._show_frames(faces.FACES["sleep"], "face · sleep (idle)", "face", "system", None, mood="sleep")
            if self.effective_brightness(now_dt) != self._bright_sent:
                self.cv.notify_all()

    def _check_reminders(self, now_dt, now):
        hm = now_dt.strftime("%H:%M")
        for r in self.settings.snapshot()["reminders"]:
            if not isinstance(r, dict) or not r.get("enabled", True) or r.get("time") != hm:
                continue
            days = r.get("days") if isinstance(r.get("days"), list) and r.get("days") else list(range(7))
            key = (now_dt.date(), hm, str(r.get("id")))
            if now_dt.weekday() not in days or key in self._fired:
                continue
            self._fired.add(key)
            self._fired = {k for k in self._fired if k[0] == now_dt.date()}
            restore = self.restore_req if not self.temp else self.temp["restore"]
            text, secs = str(r.get("text", "")).strip(), max(5, min(300, _to_int(r.get("seconds", 20), 20)))
            if text:
                frames = faces.text_frames(text, faces.CORAL)
            else:
                frames = faces.FACES.get(r.get("mood"), faces.FACES["attention"])
            self._show_frames(frames, f"reminder · {text or r.get('mood', 'attention')}", "face", "system", None)
            self.temp = {"until": now + secs, "restore": restore}
            self.events.append({"type": "reminder", "label": text or "reminder", "t": now})

    # ---- Claude Code live status ---------------------------------------------------------
    def _handle_event(self, req, source):
        if source not in ("hook", "gui", "system"):
            return {"ok": False, "denied": "only the status hooks may send events", "connected": self.connected}
        now = self.clock()
        try:
            self._record_event(req, now)
        except (ValueError, TypeError, OverflowError) as e:
            return {"ok": False, "error": str(e)}
        self.last_activity = now
        if self._scene_allowed():
            self._scene_update(now, req)
        return {"ok": True, "connected": self.connected}

    def _scene_allowed(self):
        cfg = self.settings.snapshot()["claude"]
        return policy.decide(cfg, {"cmd": "event"}, "hook", self.pinned, datetime.datetime.now(),
                             self.last_change, self.clock())[0]

    def _scene_blocked(self, now):
        return self.app is not None or now < self.hold_until or self.temp is not None or self.nlight_active

    def _new_session(self, sid, now):
        used = {x["color_idx"] for x in self.sessions.values()}
        idx = next((i for i in range(len(scene.ACCENTS)) if i not in used), len(self.sessions) % len(scene.ACCENTS))
        return {"id": sid, "project": "", "cwd": "", "state": "idle", "kind": None, "tool": None, "task_start": None,
                "attention_since": None, "agents": 0, "beats": [], "last_event": now, "last_ts": 0.0, "since": now,
                "color_idx": idx, "color": scene.ACCENTS[idx]}

    def _flash(self, mood_key, frames, secs, now):
        cfg = self.settings.snapshot()
        if not cfg["scene"]["reactions"] or (mood_key and not cfg["claude"]["moods"].get(mood_key, True)):
            return
        self.flash = {"frames": frames, "until": now + secs}

    def _record_event(self, ev, now):
        """Update session bookkeeping from one hook event. Always runs, whatever the permissions say."""
        name = str(ev.get("event", ""))
        sid = str(ev.get("session") or "default")[:64]
        if name == "SessionEnd":
            self.sessions.pop(sid, None)
            self.scene_dirty = True
            return
        s = self.sessions.get(sid)
        if s is None:
            if len(self.sessions) >= 50:  # a local caller must not be able to grow this without limit
                del self.sessions[min(self.sessions, key=lambda k: self.sessions[k]["last_event"])]
            s = self.sessions[sid] = self._new_session(sid, now)
        cwd = str(ev.get("cwd") or "")
        if cwd:
            s["cwd"] = cwd
            s["project"] = os.path.basename(cwd.rstrip("/\\"))[:30]
        ts = ev.get("ts")
        ts = float(ts) if isinstance(ts, (int, float)) and not isinstance(ts, bool) and abs(ts) < 1e12 else now
        ts = min(ts, now)  # an event cannot have happened after we received it, so a future stamp cannot freeze a session
        fresh = ts >= s["last_ts"]  # hooks run asynchronously, so a late arrival must not undo newer state
        s["last_ts"] = max(s["last_ts"], ts)
        s["last_event"] = now

        def set_state(st):
            if fresh:
                s["state"], s["since"] = st, now

        kind = ev.get("kind") if ev.get("kind") in faces.GLYPH_KINDS else None
        scfg = self.settings.snapshot()["scene"]
        if name == "SessionStart":
            set_state("idle")
            if len(self.sessions) == 1:
                self._flash("splash", faces.FACES["splash"], 2.5, now)
        elif name == "UserPromptSubmit":
            set_state("thinking")
            if fresh:
                s.update(task_start=now, tool=None, kind=None, attention_since=None)
        elif name == "PreToolUse":
            set_state("working")
            if fresh:
                s["tool"], s["kind"], s["attention_since"] = str(ev.get("tool") or "")[:40] or None, kind, None
                s["task_start"] = s["task_start"] or now
            s["beats"] = [t for t in s["beats"] if now - t < 100] + [now]
        elif name == "PostToolUse":
            if s["state"] == "attention":
                set_state("working")
                s["attention_since"] = None
            tests = ev.get("tests")
            if kind == "test" and tests and scfg.get("test_results", True):
                self._flash(None, [(faces.tests_frame(int(tests[0]), int(tests[1])), 4000)], 4, now)
            elif kind == "test" or ev.get("push"):
                self._flash("party", faces.FACES["party"], 2.5, now)
            if ev.get("push") and scfg["ci_dot"] and self.use_threads:
                self.ci_watch.watch(cwd or s.get("cwd"))
        elif name == "PostToolUseFailure":
            if s["state"] == "attention":
                set_state("working")
                s["attention_since"] = None
            s["beats"] = [t for t in s["beats"] if now - t < 100] + [now]
            tests = ev.get("tests")
            if kind == "test" and tests and scfg.get("test_results", True):
                self._flash(None, [(faces.tests_frame(int(tests[0]), int(tests[1])), 4000)], 4, now)
            else:
                self._flash("error", faces.FACES["error"], 1.3, now)
        elif name == "Notification":
            if ev.get("ntype") in (None, "", "permission_prompt", "idle_prompt", "elicitation_dialog",
                                   "agent_needs_input"):
                set_state("attention")
                if fresh:
                    s["attention_since"] = s["attention_since"] or now
        elif name == "SubagentStart":
            s["agents"] += 1
        elif name == "SubagentStop":
            s["agents"] = max(0, s["agents"] - 1)
        elif name == "Stop":
            set_state("done")
            if fresh:
                s.update(task_start=None, tool=None, kind=None, attention_since=None, agents=0)
        self.scene_dirty = True

    def _scene_update(self, now, ev):
        if self._scene_blocked(now):
            s = self.sessions.get(str(ev.get("session") or "default")[:64])
            if (ev.get("event") == "Notification" and s and s["state"] == "attention" and self.temp is None
                    and self.settings.snapshot()["claude"]["moods"].get("attention", True)):
                # you need to act: break through whatever is on screen for a few seconds, then go back
                restore = self.restore_req
                self._show_frames(faces.FACES["attention"], "Claude needs you", "face", "hook", None, keep_app=True)
                self.temp = {"until": now + 8, "restore": restore}
            return
        self._render_scene(now)

    def _render_scene(self, now, force=False):
        snap = self.settings.snapshot()
        ctx = {"now": now, "cfg": snap["scene"], "moods": snap["claude"]["moods"], "ci": self._ci_visible(now)}
        if self.flash and now < self.flash["until"]:
            frames, label = self.flash["frames"], "Claude · reaction"
        else:
            self.flash = None
            frames, label = scene.render(list(self.sessions.values()), ctx)
        packets = protocol.display_packets(frames)
        self.scene_dirty, self.scene_last = False, now
        if packets == self.out["packets"] and self.scene_active and not force:
            self.current["label"] = label
            return
        self._show_packets(packets, label, "scene", "hook", None, frames=frames, quiet=True, scene=True)
        base = label.split(" (")[0]
        if base != self._scene_logged:
            self._scene_logged = base
            self._log("hook", base)

    def _scene_tick(self, now):
        if self.flash and now >= self.flash["until"]:
            self.flash = None
            self.scene_dirty = True
        snap = self.settings.snapshot()
        sleep_after = snap["idle_sleep_minutes"] * 60
        for sid in [k for k, s in self.sessions.items() if now - s["last_event"] > 3 * 3600 and s["state"] != "working"]:
            del self.sessions[sid]
            self.scene_dirty = True
        if sleep_after > 0:
            for s in self.sessions.values():
                if s["state"] in ("idle", "done", "error") and now - s["last_event"] > sleep_after:
                    s["state"] = "sleep"
                    self.scene_dirty = True
        if not self.sessions or self._scene_blocked(now) or not self._scene_allowed():
            return
        if not self.scene_active:
            self.scene_dirty = True
        busy = any(s["state"] in ("thinking", "working", "attention") for s in self.sessions.values())
        if (self.scene_dirty and now - self.scene_last >= 1.0) or (busy and now - self.scene_last >= 5.0):
            self._render_scene(now)

    def _scene_request(self, req, source):
        action = req.get("action")
        if action == "resume":
            self.app, self.temp, self.flash, self.hold_until = None, None, None, 0.0
            self._log(source, "Claude's live status resumed")
            self._render_scene(self.clock(), force=True)
        elif action == "dismiss_ci":
            self.ci = None
            self.scene_dirty = True
        else:
            raise ValueError(f"unknown scene action {action!r}")

    # ---- night light (fork ZERO) --------------------------------------------------------
    def _nightlight_request(self, req, source):
        """Enable/disable, or force on/off now. Options live in settings["nightlight"]."""
        action = req.get("action", "enable")
        s = self.settings.snapshot()["nightlight"]
        if action == "enable":
            self.settings.patch({"nightlight": {"enabled": True}})
            self._nightlight_on(100 if s["fade_min"] <= 0 else 25)   # start bright-ish, fade finishes itself
            self.nlight_until = self.clock() + 3600 * 24 * 365        # stay until window or disable
            self._log(source, "night light enabled")
        elif action == "disable":
            self.settings.patch({"nightlight": {"enabled": False}})
            self.nlight_until = 0.0
            self.nlight_active = False
            self._apply({"cmd": "face", "mood": "idle"}, "system")
            self._log(source, "night light disabled")
        elif action == "on":
            self.nlight_until = self.clock() + _to_int(req.get("minutes", 0), 0) * 60 + 3600 * 24 * 365
            self._nightlight_on(100 if s["fade_min"] <= 0 else 25)
            self._log(source, "night light on now")
        elif action == "off":
            self.nlight_until = 0.0
            self.nlight_active = False
            self._apply({"cmd": "face", "mood": "idle"}, "system")
            self._log(source, "night light off now")
        else:
            raise ValueError(f"unknown nightlight action {action!r}")
        self.cv.notify_all()

    def _nightlight_in_window(self, now_dt):
        s = self.settings.snapshot()["nightlight"]
        if s["mode"] == "always":
            return True
        return policy.in_window(now_dt.strftime("%H:%M"), s["start"], s["end"])

    def _nightlight_on(self, bright_scale):
        s = self.settings.snapshot()["nightlight"]
        b = max(1, min(100, int(s["brightness"] * bright_scale / 100)))
        if s["style"] == "effect":
            self.cmds.append(protocol.effect_packet(max(0, min(len(protocol.EFFECTS) - 1, int(s["kind"], 0)))))
        else:
            self.cmds.append(protocol.light_packet(_rgb(s.get("color"), (255, 154, 60)), b,
                                                   max(0, min(4, int(s.get("kind", 0)))), True))
        self.cv.notify_all()

    def _nightlight_tick(self, now_dt, now):
        s = self.settings.snapshot()["nightlight"]
        wanted = s["enabled"] and (self._nightlight_in_window(now_dt) or now < self.nlight_until)
        if wanted and not self.nlight_active:
            self.nlight_active = True
            self._nightlight_on(100 if s["fade_min"] <= 0 else 25)
            self.nlight_fade_at = now + 60 * max(0, s["fade_min"]) // 3   # 1/3, 2/3, full
            self.nlight_fade_step = 0
        elif wanted and self.nlight_active:
            if self.nlight_fade_at and now >= self.nlight_fade_at and self.nlight_fade_step < 2:
                self.nlight_fade_step += 1
                self._nightlight_on([25, 60, 100][self.nlight_fade_step])
                self.nlight_fade_at = now + 60 * max(0, s["fade_min"]) // 3
        elif not wanted and self.nlight_active:
            self.nlight_active = False
            self.nlight_until = 0.0
            self._apply({"cmd": "face", "mood": "sleep" if now_dt.hour >= 23 or now_dt.hour < 7 else "idle"}, "system")

    def _ci_visible(self, now):
        c = self.ci
        if not c:
            return None
        if c["state"] == "success" and now - c["since"] > 60:
            return None
        if c["state"] == "failure" and now - c["since"] > 1800:
            return None
        return dict(c)

    def _sessions_view(self):
        now = self.clock()
        out = []
        for s in scene.pick_order(list(self.sessions.values())):
            busy = s["state"] in ("thinking", "working") and s.get("task_start")
            out.append({"id": s["id"], "project": s["project"], "state": s["state"], "tool": s["tool"], "kind": s["kind"],
                        "color": list(s["color"]), "agents": s["agents"], "idle_for": now - s["last_event"],
                        "elapsed": now - s["task_start"] if busy else None,
                        "waiting_for": now - s["attention_since"] if s.get("attention_since") else None})
        return out

    # ---- callbacks from the background watchers ------------------------------------------
    def ci_update(self, info, finished=False):
        with self.cv:
            prev, self.ci = self.ci, info
            now = self.clock()
            if info and (not prev or prev.get("sha") != info.get("sha")):
                self._log("system", f"CI: watching {info['repo']}@{info['branch']}")
            if info and finished:
                ok = info["state"] == "success"
                self._log("system", f"CI {'passed' if ok else 'FAILED'} · {info['repo']}", ok)
                self.events.append({"type": "ci", "label": f"CI {'passed' if ok else 'failed'}: {info['repo']}"})
                self._flash("party" if ok else "error", faces.FACES["party" if ok else "error"], 4, now)
            self.scene_dirty = True
            self.cv.notify_all()

    def monitor_event(self, name, up):
        with self.cv:
            now = self.clock()
            self._log("system", f"site {name} is {'back up' if up else 'DOWN'}", up)
            self.events.append({"type": "site", "label": f"{name} is {'back up' if up else 'DOWN'}"})
            if not up and self.settings.snapshot()["monitors"]["alert"]:
                restore = self.restore_req if not self.temp else self.temp["restore"]
                frames = faces.text_frames(f"{name} DOWN", faces.RED)
                self._show_frames(frames, f"alert · {name} is down", "face", "system", None, keep_app=True)
                self.temp = {"until": now + 12, "restore": restore}

    def weather_update(self, temp, wtype, city, error=None):
        with self.cv:
            self.weather_state = {"city": city, "temp": temp, "sky": wtype, "error": error, "t": self.clock()}
            if temp is not None:
                self.cmds.append(protocol.weather_packet(temp, wtype))
                self.cv.notify_all()

    def settings_changed(self):
        self.uptime.wake.set()
        self.weather.wake.set()
        with self.cv:
            self.scene_dirty = True

    def _net_probe_async(self):
        if self._net_busy or not self.use_threads:
            return
        self._net_busy = True

        def probe():
            ms = monitors.probe_latency()
            with self.cv:
                self.net_samples.append(ms)
                self._net_busy = False
        threading.Thread(target=probe, daemon=True, name="netprobe").start()

    # ---- GUI snapshots ------------------------------------------------------------------
    def state(self, drain=True):
        with self.cv:
            s = self.settings.snapshot()
            app = None
            if self.app:
                app = {"name": self.app["name"]}
                if self.app["name"] == "timer":
                    app["timer"] = self.timer_info()
                if self.app["name"] == "sysmon":
                    app["cpu"], app["ram"] = self.app["state"].get("cpu"), self.app["state"].get("ram")
            events = list(self.events)
            if drain:
                self.events = []
            return {
                "connected": self.connected, "error": self.last_error, "address": s["device"]["address"],
                "pinned": self.pinned, "brightness": s["brightness"], "effective_brightness": self.effective_brightness(),
                "current": {**self.current, "preview_id": self.preview["id"], "age": self.clock() - self.current["since"]},
                "app": app, "scoreboard": self.scoreboard, "events": events, "log": list(self.log)[:60],
                "uptime": self.clock() - self.started,
                "sessions": self._sessions_view(),
                "scene": {"active": self.scene_active, "held": self.app is not None or self.clock() < self.hold_until,
                          "holding_for": None if self.clock() >= self.hold_until else
                          ("forever" if self.hold_until == float("inf") else round(self.hold_until - self.clock()))},
                "ci": self._ci_visible(self.clock()),
                "monitors": self.uptime.snapshot(),
                "weather": self.weather_state,
            }

    def get_preview(self):
        with self.cv:
            fr = self.preview["frames"]
            return {"id": self.preview["id"],
                    "frames": None if fr is None else [
                        {"hex": "".join("%02x%02x%02x" % tuple(p) for p in px), "delay": d} for px, d in fr[:60]]}

    # ---- Bluetooth worker ---------------------------------------------------------------
    def start(self):
        if not self.use_threads:
            return
        threading.Thread(target=self._bt_loop, daemon=True, name="bluetooth").start()
        threading.Thread(target=self._tick_loop, daemon=True, name="ticker").start()
        self.uptime.start()
        self.weather.start()

    def stop(self):
        self.quit.set()
        self.uptime.wake.set()
        self.weather.wake.set()
        with self.cv:
            self.cv.notify_all()

    def request_reconnect(self):
        with self.cv:
            self.reconnect_flag = True
            self.cv.notify_all()

    def _auto_discover(self):
        """First run: if exactly one Divoom speaker is paired, use it. Tries at most once a minute."""
        if time.time() - self._last_discover < 60:
            return
        self._last_discover = time.time()
        found = discover.find_speakers()
        if len(found) == 1:
            self.settings.patch({"device": {"address": found[0]["address"]}})
            with self.cv:
                self._log("system", f"found your speaker: {found[0]['name']}")

    def _tick_loop(self):
        while not self.quit.is_set():
            try:
                self.tick()
            except Exception as e:  # a bad tick must never kill the loop
                if repr(e) != self._last_tick_error:  # say it once, not four times a second
                    self._last_tick_error = repr(e)
                    with self.cv:
                        self._log("system", "internal error", False, repr(e))
            self.quit.wait(0.25)

    def _bt_loop(self):
        last = None
        while not self.quit.is_set():
            try:
                self._bt_session()
            except Exception as e:  # never leave the speaker without a worker
                if repr(e) != last:
                    last = repr(e)
                    with self.cv:
                        self._log("system", "bluetooth worker restarted", False, repr(e))
                self.quit.wait(2)

    def _bt_session(self):
        tb, applied, last_sent, backoff = None, -1, 0.0, 2
        while not self.quit.is_set():
            if self.reconnect_flag and tb is not None:
                tb.close()
                tb, backoff = None, 2
            self.reconnect_flag = False
            if tb is None:
                dev = self.settings.snapshot()["device"]
                if not dev["address"]:
                    self._auto_discover()
                    dev = self.settings.snapshot()["device"]
                    if not dev["address"]:
                        with self.cv:
                            self.connected = False
                            self.last_error = "No speaker chosen yet. Open Settings and press Find my speaker."
                            self.cv.wait(timeout=10)
                        continue
                try:
                    tb = self.transport(dev["address"], dev["channel"])
                    tb.connect()
                except Exception as e:
                    tb = None
                    with self.cv:
                        self.connected, self.last_error = False, f"{type(e).__name__}: {e}"
                        self.cv.wait(timeout=backoff)
                    backoff = min(backoff * 2, 30)
                    continue
                with self.cv:
                    self.connected, self.last_error = True, ""
                    self._bright_sent = None
                    self._log("system", "speaker connected")
                    if self.settings.snapshot()["sync_time_on_connect"]:
                        self.cmds.insert(0, protocol.time_packet())
                applied, backoff = -1, 2
            with self.cv:
                self.cv.wait_for(lambda: self.quit.is_set() or self.reconnect_flag or self.out["version"] != applied
                                 or self.cmds or self.effective_brightness() != self._bright_sent,
                                 timeout=5)
                version, packets, cmds = self.out["version"], self.out["packets"], self.cmds
                self.cmds = []
                bright = self.effective_brightness()
                bright_dirty = bright != self._bright_sent
            try:
                if bright_dirty:
                    tb.send(protocol.brightness_packet(bright))
                    self._bright_sent = bright
                    time.sleep(0.5)  # the speaker garbles a picture that follows a brightness change too fast
                for p in cmds:
                    tb.send(p)
                    time.sleep(0.2)
                if version != applied:
                    for p in packets:
                        tb.send(p)
                        time.sleep(0.15)
                    applied = version
                    last_sent = time.time()
                elif time.time() - last_sent > 40:
                    tb.send(protocol.brightness_packet(bright))  # keeps the Bluetooth link from sleeping
                    last_sent = time.time()
            except Exception as e:
                with self.cv:
                    self.connected, self.last_error = False, f"{type(e).__name__}: {e}"
                    self._log("system", "speaker connection lost", False, str(e))
                try:
                    tb.close()
                except Exception:
                    pass
                tb = None
        if tb:
            tb.close()
