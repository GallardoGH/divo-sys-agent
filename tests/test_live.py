import datetime
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from divosys import faces, hook, monitors, policy, protocol, scene, toolinfo  # noqa: E402
from divosys.engine import Engine  # noqa: E402
from divosys.settings import Settings, _merge, defaults  # noqa: E402


class FakeBox:
    def __init__(self, *a):
        pass

    def connect(self):
        pass

    def send(self, *p):
        pass

    def close(self):
        pass


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


def new_engine():
    clock = Clock()
    settings = Settings(os.path.join(tempfile.mkdtemp(), "s.json"))
    return Engine(settings, FakeBox, clock, threads=False), clock


def ev(name, sid="a", **kw):
    return {"cmd": "event", "event": name, "session": sid, "cwd": "C:/work/proj", **kw}


class ToolInfo(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(toolinfo.tool_kind("Bash", "ls -la"), "bash")
        self.assertEqual(toolinfo.tool_kind("Bash", "python -m pytest -q"), "test")
        self.assertEqual(toolinfo.tool_kind("Bash", "npm run test"), "test")
        self.assertEqual(toolinfo.tool_kind("Bash", "git status"), "git")
        self.assertEqual(toolinfo.tool_kind("Edit"), "edit")
        self.assertEqual(toolinfo.tool_kind("WebFetch"), "web")
        self.assertEqual(toolinfo.tool_kind("Grep"), "search")
        self.assertIsNone(toolinfo.tool_kind("mcp__thing__go"))

    def test_push(self):
        self.assertTrue(toolinfo.is_push("git push origin main"))
        self.assertTrue(toolinfo.is_push("cd x && git push"))
        self.assertFalse(toolinfo.is_push("git pull"))

    def test_parse_runners(self):
        self.assertEqual(toolinfo.parse_test_output("===== 5 passed, 1 failed, 2 errors in 0.3s ====="), (5, 3))
        self.assertEqual(toolinfo.parse_test_output("===== 12 passed in 1.2s ====="), (12, 0))
        self.assertEqual(toolinfo.parse_test_output("Ran 30 tests in 4.1s\n\nOK"), (30, 0))
        self.assertEqual(toolinfo.parse_test_output("Ran 30 tests in 4.1s\n\nFAILED (failures=2, errors=1)"), (27, 3))
        self.assertEqual(toolinfo.parse_test_output("Tests:       1 failed, 5 passed, 6 total"), (5, 1))
        self.assertEqual(toolinfo.parse_test_output("test result: ok. 12 passed; 0 failed; 0 ignored\n"
                                                    "test result: FAILED. 3 passed; 2 failed;"), (15, 2))
        self.assertIsNone(toolinfo.parse_test_output("nothing useful here"))
        self.assertIsNone(toolinfo.parse_test_output(""))


class HookBuild(unittest.TestCase):
    def test_pre_tool(self):
        r = hook.build({"hook_event_name": "PreToolUse", "session_id": "s1", "cwd": "C:/x/y", "tool_name": "Bash",
                        "tool_input": {"command": "pytest -q"}})
        self.assertEqual((r["cmd"], r["event"], r["kind"], r["session"]), ("event", "PreToolUse", "test", "s1"))

    def test_post_push_and_tests(self):
        r = hook.build({"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "git push"},
                        "tool_response": {"stdout": "ok", "stderr": ""}})
        self.assertTrue(r["push"])
        r = hook.build({"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "pytest"},
                        "tool_response": {"stdout": "== 7 passed in 1s ==", "stderr": ""}})
        self.assertEqual(r["tests"], [7, 0])

    def test_failure_reads_error_text(self):
        r = hook.build({"hook_event_name": "PostToolUseFailure", "tool_name": "Bash",
                        "tool_input": {"command": "python -m unittest"}, "error": "Exit code 1\nRan 4 tests\nFAILED (failures=1)"})
        self.assertEqual(r["tests"], [3, 1])

    def test_notification_and_legacy(self):
        self.assertEqual(hook.build({"hook_event_name": "Notification", "notification_type": "permission_prompt"})["ntype"],
                         "permission_prompt")
        self.assertEqual(hook.build({}, "thinking"), {"cmd": "face", "mood": "thinking"})


class SceneRender(unittest.TestCase):
    def ctx(self, **cfg):
        c = defaults()["scene"]
        c.update(cfg)
        return {"now": 1000.0, "cfg": c, "moods": {m: True for m in faces.MOODS}, "ci": None}

    def sess(self, **kw):
        s = {"id": "a", "project": "p", "state": "working", "kind": "bash", "tool": "Bash", "task_start": 990.0,
             "attention_since": None, "agents": 0, "beats": [], "last_event": 1000.0, "color": (0, 200, 255)}
        s.update(kw)
        return s

    def test_frames_are_well_formed(self):
        for state in ("idle", "thinking", "working", "attention", "done", "error", "sleep"):
            for px, d in scene.render_single(self.sess(state=state), self.ctx()):
                self.assertEqual(len(px), 256)
                self.assertGreater(d, 0)

    def test_working_adds_glyph_frame_and_overlays(self):
        s = self.sess(agents=2, beats=[999.0, 998.5, 998.4])
        frames = scene.render_single(s, self.ctx())
        self.assertEqual(frames[-1][0], faces.glyph_frame("bash"))
        first = frames[0][0]
        self.assertEqual(first[0 * 16 + 1], faces.CREAM)            # sub-agent dot
        self.assertEqual(first[15 * 16 + 15], faces.CREAM)          # newest heartbeat column has a spark
        self.assertEqual(first[15 * 16 + 0], faces.TRACK)           # quiet columns show a baseline

    def test_each_tool_picture_can_be_switched_off(self):
        s = self.sess(kind="bash")
        off = scene.render_single(s, self.ctx(tool_pictures={"bash": False}))
        on = scene.render_single(s, self.ctx(tool_pictures={"bash": True}))
        self.assertEqual(len(off), len(faces.FACES["working"]))      # face only
        self.assertEqual(len(on), len(faces.FACES["working"]) + 1)   # face plus the picture
        other = scene.render_single(self.sess(kind="edit"), self.ctx(tool_pictures={"bash": False}))
        self.assertEqual(len(other), len(faces.FACES["working"]) + 1)  # other tools keep theirs

    def test_toggles_remove_overlays(self):
        s = self.sess(agents=2, beats=[999.0])
        frames = scene.render_single(s, self.ctx(glyphs=False, heartbeat=False, agent_dots=False))
        self.assertEqual(len(frames), len(faces.FACES["working"]))
        self.assertNotEqual(frames[0][0][1], faces.CREAM)

    def test_long_task_sweats_and_the_elapsed_clock_is_opt_in(self):
        s = self.sess(task_start=1000.0 - 200)
        frames = scene.render_single(s, self.ctx())
        self.assertEqual(len(frames), len(faces.FACES["sweat"]) + 1)  # sweat frames and the tool glyph, no clock
        frames = scene.render_single(s, self.ctx(elapsed_clock=True))
        self.assertEqual(len(frames), len(faces.FACES["sweat"]) + 2)  # ...and now the elapsed clock too

    def test_attention_hops_and_never_flashes(self):
        from divosys import zerofaces as Z
        fresh = scene.render_single(self.sess(state="attention", attention_since=990.0), self.ctx())
        long_wait = scene.render_single(self.sess(state="attention", attention_since=100.0), self.ctx())
        self.assertEqual([p for p, _ in fresh], [p for p, _ in long_wait])  # waiting longer changes nothing
        self.assertEqual(len(fresh), len(faces.FACES["attention"]))
        for px, _ in fresh:
            self.assertGreater(px.count((255, 179, 0)), 0)   # amber sparkles in every frame
            self.assertIn((255, 255, 255), px)               # ZERO's white sclera is in every frame

    def test_an_old_nag_setting_is_ignored(self):
        merged = _merge(defaults(), {"scene": {"nag_after_s": 5}})
        self.assertNotIn("nag_after_s", merged["scene"])

    def test_disabled_mood_falls_back_to_idle(self):
        c = self.ctx()
        c["moods"]["working"] = False
        frames = scene.render_single(self.sess(kind=None), c)
        self.assertEqual(len(frames), len(faces.FACES["idle"]))

    def test_board_layouts(self):
        for n in (2, 3, 4):
            sessions = [self.sess(id=str(i), color=scene.ACCENTS[i]) for i in range(n)]
            frames, label = scene.render(sessions, self.ctx())
            self.assertEqual(len(frames), 2)
            self.assertIn(f"{n} sessions", label)
            row = 4 if n == 2 else 0  # two sessions sit side by side in the middle, three or four fill the quadrants
            self.assertEqual(frames[0][0][row * 16 + 3], scene.ACCENTS[0])  # first session's accent stripe

    def test_single_mode_ignores_board(self):
        sessions = [self.sess(id="a"), self.sess(id="b", state="idle")]
        frames, label = scene.render(sessions, self.ctx(mode="single"))
        self.assertIn("working", label)

    def test_ci_dot(self):
        c = self.ctx()
        c["ci"] = {"state": "success"}
        frames = scene.render_single(self.sess(state="done"), c)
        self.assertEqual(frames[0][0][0 * 16 + 15], faces.GREEN)

    def test_no_sessions_sleeps(self):
        frames, label = scene.render([], self.ctx())
        self.assertIn("no sessions", label)


class LiveEngine(unittest.TestCase):
    def setUp(self):
        self.e, self.clock = new_engine()

    def send(self, name, sid="a", source="hook", **kw):
        return self.e.handle(ev(name, sid, **kw), source)

    def test_prompt_tool_stop_cycle(self):
        self.assertTrue(self.send("UserPromptSubmit")["ok"])
        self.assertEqual(self.e.sessions["a"]["state"], "thinking")
        self.assertEqual(self.e.current["kind"], "scene")
        self.assertIn("proj · thinking", self.e.current["label"])
        self.send("PreToolUse", tool="Bash", kind="bash")
        self.assertIn("(Bash)", self.e.current["label"])
        self.send("Stop")
        self.assertIn("done", self.e.current["label"])
        self.assertEqual(self.e.sessions["a"]["task_start"], None)

    def test_two_sessions_make_a_board(self):
        self.send("UserPromptSubmit", sid="a")
        self.send("UserPromptSubmit", sid="b")
        self.assertIn("2 sessions", self.e.current["label"])
        self.assertNotEqual(self.e.sessions["a"]["color"], self.e.sessions["b"]["color"])
        self.send("SessionEnd", sid="b")
        self.assertIn("proj", self.e.current["label"])

    def test_session_end_of_last_shows_sleep(self):
        self.send("UserPromptSubmit")
        self.send("SessionEnd")
        self.assertEqual(self.e.sessions, {})
        self.assertIn("no sessions", self.e.current["label"])

    def test_claude_face_holds_then_status_returns(self):
        self.send("UserPromptSubmit")
        self.assertTrue(self.e.handle({"cmd": "face", "mood": "party"}, "mcp")["ok"])
        self.send("PreToolUse", tool="Edit", kind="edit")
        self.assertEqual(self.e.current["kind"], "face")  # Claude's own choice is not stomped at once
        self.clock.t += 31
        self.e.tick()
        self.assertEqual(self.e.current["kind"], "scene")

    def test_gui_mode_holds_until_resume(self):
        self.send("UserPromptSubmit")
        self.e.handle({"cmd": "mode", "mode": "clock"}, "gui")
        self.clock.t += 3600
        self.send("PreToolUse", tool="Bash", kind="bash")
        self.e.tick()
        self.assertEqual(self.e.current["kind"], "mode")
        st = self.e.state()
        self.assertTrue(st["scene"]["held"])
        self.assertEqual(st["scene"]["holding_for"], "forever")
        self.e.handle({"cmd": "scene", "action": "resume"}, "gui")
        self.assertEqual(self.e.current["kind"], "scene")

    def test_claude_cannot_resume_or_event_as_mcp(self):
        self.assertIn("denied", self.e.handle({"cmd": "scene", "action": "resume"}, "mcp"))
        self.assertIn("denied", self.e.handle(ev("Stop"), "mcp"))

    def test_attention_breaks_through_a_running_timer(self):
        self.send("UserPromptSubmit")
        self.e.handle({"cmd": "timer", "action": "start", "seconds": 600}, "gui")
        self.send("Notification", ntype="permission_prompt")
        self.assertEqual(self.e.current["label"], "Claude needs you")
        self.assertIsNotNone(self.e.temp)
        self.assertIsNotNone(self.e.app)            # the timer keeps running underneath
        self.clock.t += 9
        self.e.tick()
        self.assertIsNone(self.e.temp)
        self.assertIn("timer", self.e.current["label"])  # and comes back

    def test_pin_stops_display_but_not_bookkeeping(self):
        self.e.handle({"cmd": "pin", "value": True}, "gui")
        self.send("PreToolUse", tool="Bash", kind="bash")
        self.assertEqual(self.e.sessions["a"]["state"], "working")
        self.assertNotEqual(self.e.current["kind"], "scene")
        self.e.handle({"cmd": "pin", "value": False}, "gui")
        self.send("PreToolUse", tool="Bash", kind="bash")
        self.assertEqual(self.e.current["kind"], "scene")

    def test_master_switch_stops_display_but_not_bookkeeping(self):
        self.e.settings.patch({"claude": {"enabled": False}})
        self.send("UserPromptSubmit")
        self.assertIn("a", self.e.sessions)
        self.assertNotEqual(self.e.current["kind"], "scene")

    def test_late_events_do_not_undo_newer_state(self):
        self.send("UserPromptSubmit", ts=10.0)
        self.send("Stop", ts=20.0)
        self.send("PreToolUse", ts=15.0, tool="Bash", kind="bash")  # arrived late
        self.assertEqual(self.e.sessions["a"]["state"], "done")

    def test_permission_granted_clears_attention(self):
        self.send("UserPromptSubmit")
        self.send("Notification", ntype="permission_prompt")
        self.assertEqual(self.e.sessions["a"]["state"], "attention")
        self.send("PostToolUse", tool="Bash", kind="bash")
        self.assertEqual(self.e.sessions["a"]["state"], "working")
        self.assertIsNone(self.e.sessions["a"]["attention_since"])

    def test_unrelated_notifications_ignored(self):
        self.send("UserPromptSubmit")
        self.send("Notification", ntype="auth_success")
        self.assertEqual(self.e.sessions["a"]["state"], "thinking")

    def test_subagent_counter(self):
        self.send("SubagentStart")
        self.send("SubagentStart")
        self.send("SubagentStop")
        self.assertEqual(self.e.sessions["a"]["agents"], 1)
        self.send("SubagentStop")
        self.send("SubagentStop")
        self.assertEqual(self.e.sessions["a"]["agents"], 0)

    def test_reactions(self):
        self.send("UserPromptSubmit")
        self.send("PostToolUse", tool="Bash", kind="test", tests=[30, 0])
        self.assertEqual(self.e.current["label"], "Claude · reaction")
        self.clock.t += 5
        self.e.tick()
        self.assertNotEqual(self.e.current["label"], "Claude · reaction")
        self.send("PostToolUse", tool="Bash", kind="git", push=True)
        self.assertIsNotNone(self.e.flash)  # party
        self.clock.t += 5
        self.e.tick()
        self.send("PostToolUseFailure", tool="Bash", kind="bash")
        self.assertIsNotNone(self.e.flash)  # glitch

    def test_reactions_can_be_switched_off(self):
        self.e.settings.patch({"scene": {"reactions": False}})
        self.send("PostToolUse", tool="Bash", kind="git", push=True)
        self.assertIsNone(self.e.flash)
        self.e.settings.patch({"scene": {"reactions": True}, "claude": {"moods": {"party": False}}})
        self.send("PostToolUse", tool="Bash", kind="git", push=True)
        self.assertIsNone(self.e.flash)

    def test_test_results_can_be_switched_off_on_their_own(self):
        self.e.settings.patch({"scene": {"test_results": False}})
        self.send("PostToolUse", tool="Bash", kind="test", tests=[41, 0])
        self.assertEqual(self.e.flash["frames"], faces.FACES["party"])   # confetti, not the result screen
        self.clock.t += 5
        self.e.tick()
        self.send("PostToolUseFailure", tool="Bash", kind="test", tests=[40, 1])
        self.assertEqual(self.e.flash["frames"], faces.FACES["error"])   # the glitch
        self.clock.t += 5
        self.e.tick()
        self.e.settings.patch({"scene": {"test_results": True}})
        self.send("PostToolUse", tool="Bash", kind="test", tests=[41, 0])
        self.assertEqual(self.e.flash["frames"][0][0], faces.tests_frame(41, 0))

    def test_idle_sessions_fall_asleep(self):
        self.e.settings.patch({"idle_sleep_minutes": 1})
        self.send("Stop")
        self.clock.t += 120
        self.e.tick()
        self.assertEqual(self.e.sessions["a"]["state"], "sleep")

    def test_busy_scene_refreshes_for_the_heartbeat(self):
        self.send("PreToolUse", tool="Bash", kind="bash")
        v = self.e.out["version"]
        self.clock.t += 6
        self.e.tick()
        self.assertGreater(self.e.out["version"], v)

    def test_state_is_json_serialisable(self):
        self.send("UserPromptSubmit")
        self.send("PreToolUse", tool="Bash", kind="bash")
        st = self.e.state()
        json.dumps(st)
        self.assertEqual(st["sessions"][0]["project"], "proj")

    def test_ci_visibility(self):
        now = self.clock()
        self.e.ci_update({"state": "success", "repo": "r", "branch": "main", "sha": "abc", "since": now, "url": ""}, finished=True)
        self.assertTrue(any(x["type"] == "ci" for x in self.e.events))  # before state() hands the notices out
        self.assertIsNotNone(self.e.state()["ci"])
        self.clock.t += 61
        self.assertIsNone(self.e.state()["ci"])
        self.e.ci_update({"state": "failure", "repo": "r", "branch": "main", "sha": "def", "since": self.clock.t, "url": ""}, finished=True)
        self.clock.t += 600
        self.assertIsNotNone(self.e.state()["ci"])  # failures stay until dismissed
        self.e.handle({"cmd": "scene", "action": "dismiss_ci"}, "gui")
        self.assertIsNone(self.e.state()["ci"])

    def test_site_down_alerts_then_restores(self):
        self.e.handle({"cmd": "face", "mood": "done"}, "gui")
        self.e.monitor_event("my-site", False)
        self.assertIn("my-site", self.e.current["label"])
        self.assertIsNotNone(self.e.temp)
        self.clock.t += 13
        self.e.tick()
        self.assertEqual(self.e.current["mood"], "done")
        self.e.monitor_event("my-site", True)
        self.assertTrue(self.e.log[0]["ok"])

    def test_alert_can_be_switched_off(self):
        self.e.settings.patch({"monitors": {"alert": False}})
        self.e.monitor_event("x", False)
        self.assertIsNone(self.e.temp)

    def test_weather_update_queues_a_packet(self):
        self.e.weather_update(31, "clear", "Testville")
        self.assertEqual(self.e.cmds[-1], protocol.weather_packet(31, "clear"))
        self.assertEqual(self.e.state()["weather"]["temp"], 31)

    def test_new_apps_start_and_draw(self):
        for name in ("storage", "monitors", "net"):
            self.assertTrue(self.e.handle({"cmd": "app", "name": name, "action": "start"}, "gui")["ok"], name)
            self.assertEqual(self.e.app["name"], name)
            self.assertEqual(self.e.current["kind"], "app")
        self.assertFalse(self.e.handle({"cmd": "app", "name": "nope", "action": "start"}, "gui")["ok"])


class Policy(unittest.TestCase):
    def test_hook_event_allowed_other_commands_not(self):
        cfg = defaults()["claude"]
        now = datetime.datetime(2026, 1, 1, 12, 0)
        self.assertTrue(policy.decide(cfg, {"cmd": "event"}, "hook", now=now)[0])
        self.assertFalse(policy.decide(cfg, {"cmd": "text", "text": "x"}, "hook", now=now)[0])
        cfg["hooks"] = False
        self.assertFalse(policy.decide(cfg, {"cmd": "event"}, "hook", now=now)[0])


class Watchers(unittest.TestCase):
    def test_wmo_mapping(self):
        self.assertEqual(monitors.wmo_to_weather(0), "clear")
        self.assertEqual(monitors.wmo_to_weather(3), "cloudy")
        self.assertEqual(monitors.wmo_to_weather(45), "fog")
        self.assertEqual(monitors.wmo_to_weather(63), "rain")
        self.assertEqual(monitors.wmo_to_weather(81), "rain")
        self.assertEqual(monitors.wmo_to_weather(75), "snow")
        self.assertEqual(monitors.wmo_to_weather(95), "thunderstorm")

    def test_bad_url_scheme_is_down_without_a_request(self):
        up, ms, err = monitors.check_site("file:///etc/passwd")
        self.assertFalse(up)
        self.assertIn("http", err)

    def _ssl_error(self, code, msg):
        import ssl
        err = ssl.SSLCertVerificationError(1, msg)
        err.verify_code, err.verify_message = code, msg
        return urllib.error.URLError(err)

    def _fake_response(self):
        class R:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s, n=-1): return b"x"
        return R()

    def test_incomplete_local_chain_counts_as_up(self):
        calls = []

        def fake(req, timeout=None, context=None):
            calls.append(context)
            if context is None:
                raise self._ssl_error(20, "unable to get local issuer certificate")
            return self._fake_response()
        with mock.patch("urllib.request.urlopen", fake):
            up, ms, note = monitors.check_site("https://fine.test")
        self.assertTrue(up)
        self.assertIn("chain", note)
        self.assertEqual(len(calls), 2)

    def test_expired_certificate_is_down(self):
        def fake(req, timeout=None, context=None):
            raise self._ssl_error(10, "certificate has expired")
        with mock.patch("urllib.request.urlopen", fake):
            up, ms, note = monitors.check_site("https://old.test")
        self.assertFalse(up)
        self.assertIn("expired", note)

    def test_http_500_is_down_404_is_up(self):
        def make(code):
            def fake(req, timeout=None, context=None):
                raise urllib.error.HTTPError(req.full_url, code, "x", {}, None)
            return fake
        with mock.patch("urllib.request.urlopen", make(503)):
            self.assertFalse(monitors.check_site("https://a.test")[0])
        with mock.patch("urllib.request.urlopen", make(404)):
            self.assertTrue(monitors.check_site("https://a.test")[0])

    def test_uptime_states_and_two_miss_rule(self):
        e, _ = new_engine()
        e.settings.patch({"monitors": {"items": [{"id": "1", "name": "a", "url": "https://a.test", "enabled": True},
                                                   {"id": "2", "name": "b", "url": "https://b.test", "enabled": True},
                                                   {"id": "3", "name": "c", "url": "https://c.test", "enabled": False}]}})
        self.assertEqual(e.uptime.states(), ["unknown", "unknown"])
        up = e.uptime
        with up.lock:
            up.results["1"] = {"up": True, "ms": 120, "fails": 0}
            up.results["2"] = {"up": False, "ms": None, "fails": 3}
        self.assertEqual(up.states(), ["up", "down"])
        with up.lock:
            up.results["1"]["ms"] = 2500
        self.assertEqual(up.states(), ["slow", "down"])

    def test_frames_renderers(self):
        self.assertEqual(len(faces.monitor_frame(["up", "down", "slow", "unknown"] * 4)), 256)
        self.assertEqual(len(faces.net_frame([10, 100, 300, None])), 256)
        self.assertEqual(len(faces.storage_frame(50.0, True, 80.0)), 256)
        self.assertEqual(len(faces.storage_frame(None, False, 96.0)), 256)
        self.assertEqual(len(faces.tests_frame(120, 3)), 256)


class FaceDesign(unittest.TestCase):
    def setUp(self):
        from divosys import zerofaces as Z
        self.Z = Z

    def test_done_is_a_bounce_with_grin(self):
        done = faces.FACES["done"]
        self.assertGreaterEqual(len(done), 2)                       # bouncing happy frames
        for px, _ in done:
            self.assertIn((0, 255, 156), px)                        # green pupil: success
            self.assertTrue(any(px[y * 16 + x] == (255, 255, 255) for y in (6, 7, 8) for x in range(4, 12)))  # white grin band (bounces rows)

    def test_party_has_confetti_pupils_and_grin(self):
        party = faces.FACES["party"]
        self.assertEqual(len(party), 6)
        self.assertEqual(len({tuple(px) for px, _ in party}), 6)    # every frame differs: confetti falls
        for px, _ in party:
            self.assertIn((255, 61, 166), px)                       # magenta pupils

    def test_board_done_face_has_no_mouth(self):
        m = scene.mini_face("done", 0, (0, 200, 255))
        self.assertEqual(m[4][3], faces.CORAL)
        self.assertEqual(m[1][0], faces.CORAL)  # arm up

    def test_eyes_4x4_pupil_2x2_all_moods(self):
        # the fork's identity: white 4x4 eyes with a coloured 2x2 pupil (except splash)
        for mood, frames in faces.FACES.items():
            if mood in ("splash",):
                continue
            px = frames[0][0]
            if mood == "sleep":                                       # eyes shut: dim lids, not white sclera
                self.assertGreater(sum(1 for p in px if p == (120, 120, 120)), 8, mood)
                continue
            if mood == "heart":                                       # heart eyes: magenta hearts, no sclera
                self.assertGreater(sum(1 for p in px if p == (255, 61, 166)), 8, mood)
                continue
            whites = sum(1 for p in px if p == (255, 255, 255))
            pupils = [p for p in px if p in (self.Z.CYAN, self.Z.AMBER, self.Z.RED, self.Z.GREEN, self.Z.MAGENTA, self.Z.BLUE)]
            self.assertGreater(whites, 8, mood)
            if mood not in ("done",):
                self.assertGreater(len(pupils), 3, mood)            # 2x2 pupil x2 eyes


if __name__ == "__main__":
    unittest.main()
