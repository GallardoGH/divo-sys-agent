import datetime
import http.client
import json
import os
import random
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from divosys import faces, policy, protocol  # noqa: E402
from divosys.engine import Engine  # noqa: E402
from divosys.server import make_server  # noqa: E402
from divosys.settings import Settings  # noqa: E402


def reference_pixel_string(pixels, ncolors):
    """Port of getPixelString() from node-divoom-timebox-evo, as an independent check."""
    nb = max((ncolors - 1).bit_length(), 1)
    bits = "".join(format(p, "08b")[::-1][:nb] for p in pixels)
    return bytes(int(bits[i:i + 8][::-1], 2) for i in range(0, len(bits), 8))


def new_settings():
    return Settings(os.path.join(tempfile.mkdtemp(), "s.json"))


class Protocol(unittest.TestCase):
    def test_brightness_frame(self):
        self.assertEqual(protocol.brightness_packet(50).hex(), "0104007432aa0002")

    def test_pixel_packing_matches_reference(self):
        rnd = random.Random(1)
        for ncolors in (1, 2, 3, 4, 5, 9, 16, 17, 100, 256):
            pal = [(i, i, i) for i in range(ncolors)]
            idx = [rnd.randrange(ncolors) for _ in range(256)]
            self.assertEqual(protocol._pack(pal, idx), reference_pixel_string(idx, ncolors), ncolors)

    def test_image_length_field(self):
        pkt = protocol.image_packet(faces.FACES["done"][0][0])
        payload = pkt[3:-3]
        self.assertEqual(payload[:6], bytes.fromhex("44000a0a04aa"))
        self.assertEqual(int.from_bytes(payload[6:8], "little"), len(payload) - 5)

    def test_scoreboard_and_clock(self):
        self.assertEqual(protocol.scoreboard_packet(5, 300)[3:-3].hex(), "4506000500" "2c01")
        self.assertEqual(protocol.clock_packet(1, (255, 0, 0))[3:-3].hex(), "450001" "01" "01" "00" "00" "00" "ff0000")

    def test_animation_chunks_are_numbered(self):
        pk = protocol.animation_packets(faces.text_frames("HELLO"))
        self.assertGreater(len(pk), 1)
        self.assertEqual([p[6] for p in pk], list(range(len(pk))))


class Policy(unittest.TestCase):
    def setUp(self):
        self.cfg = new_settings().snapshot()["claude"]
        self.noon = datetime.datetime(2026, 1, 1, 12, 0)

    def d(self, req, source="mcp", **kw):
        kw.setdefault("now", self.noon)
        kw.setdefault("now_ts", 1000.0)
        return policy.decide(self.cfg, req, source, **kw)

    def test_gui_unrestricted(self):
        self.cfg["enabled"] = False
        self.assertTrue(self.d({"cmd": "pin"}, "gui")[0])

    def test_master_switch(self):
        self.cfg["enabled"] = False
        self.assertFalse(self.d({"cmd": "face", "mood": "idle"})[0])

    def test_hooks_only_faces_and_toggle(self):
        self.assertTrue(self.d({"cmd": "face", "mood": "idle"}, "hook")[0])
        self.assertFalse(self.d({"cmd": "text", "text": "x"}, "hook")[0])
        self.cfg["hooks"] = False
        self.assertFalse(self.d({"cmd": "face", "mood": "idle"}, "hook")[0])

    def test_pin_blocks_unless_overridable(self):
        self.assertFalse(self.d({"cmd": "face", "mood": "idle"}, pinned=True)[0])
        self.cfg["override_pin"] = True
        self.assertTrue(self.d({"cmd": "face", "mood": "idle"}, pinned=True)[0])

    def test_tool_and_mood_toggles(self):
        self.cfg["tools"]["show_text"] = False
        self.assertFalse(self.d({"cmd": "text", "text": "x"})[0])
        self.cfg["moods"]["error"] = False
        self.assertFalse(self.d({"cmd": "face", "mood": "error"})[0])
        self.assertTrue(self.d({"cmd": "face", "mood": "done"})[0])

    def test_admin_commands_denied_for_claude(self):
        self.assertFalse(self.d({"cmd": "pin", "value": True})[0])

    def test_clamps_and_trims(self):
        self.cfg["brightness_min"], self.cfg["brightness_max"], self.cfg["max_text_chars"] = 30, 60, 5
        self.assertEqual(self.d({"cmd": "brightness", "value": 100})[2]["value"], 60)
        self.assertEqual(self.d({"cmd": "brightness", "value": 0})[2]["value"], 30)
        self.assertEqual(self.d({"cmd": "text", "text": "abcdefgh"})[2]["text"], "abcde")

    def test_rate_limit_only_mcp(self):
        self.assertFalse(self.d({"cmd": "face", "mood": "idle"}, last_change=999.5)[0])
        self.assertTrue(self.d({"cmd": "face", "mood": "idle"}, "hook", last_change=999.5)[0])
        self.assertTrue(self.d({"cmd": "face", "mood": "idle"}, last_change=990)[0])

    def test_quiet_hours_wrap_midnight(self):
        self.cfg["quiet_hours"] = {"enabled": True, "start": "23:00", "end": "07:00"}
        self.assertFalse(self.d({"cmd": "face", "mood": "idle"}, now=datetime.datetime(2026, 1, 1, 23, 30))[0])
        self.assertFalse(self.d({"cmd": "face", "mood": "idle"}, now=datetime.datetime(2026, 1, 1, 3, 0))[0])
        self.assertTrue(self.d({"cmd": "face", "mood": "idle"})[0])


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


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.e = Engine(new_settings(), FakeBox, self.clock, threads=False)

    def test_face_and_denial_logged(self):
        self.assertTrue(self.e.handle({"cmd": "face", "mood": "done"}, "mcp")["ok"])
        self.assertEqual(self.e.current["mood"], "done")
        self.e.settings.patch({"claude": {"enabled": False}})
        r = self.e.handle({"cmd": "face", "mood": "error"}, "mcp")
        self.assertIn("denied", r)
        self.assertEqual(self.e.current["mood"], "done")
        self.assertFalse(self.e.log[0]["ok"])

    def test_pin_blocks_claude_but_not_gui(self):
        self.e.handle({"cmd": "pin", "value": True}, "gui")
        self.assertIn("denied", self.e.handle({"cmd": "face", "mood": "error"}, "hook"))
        self.assertTrue(self.e.handle({"cmd": "face", "mood": "error"}, "gui")["ok"])

    def test_countdown_finishes(self):
        self.e.handle({"cmd": "timer", "action": "start", "seconds": 5}, "gui")
        self.assertEqual(self.e.app["name"], "timer")
        self.clock.t += 2
        self.e.tick()
        self.assertAlmostEqual(self.e.timer_info()["remaining"], 3, places=1)
        self.clock.t += 4
        self.e.tick()
        self.assertIsNone(self.e.app)
        self.assertEqual(self.e.events[-1]["type"], "timer_done")

    def test_pause_resume(self):
        self.e.handle({"cmd": "timer", "action": "start", "seconds": 60}, "gui")
        self.clock.t += 10
        self.e.handle({"cmd": "timer", "action": "pause"}, "gui")
        self.clock.t += 30
        self.e.handle({"cmd": "timer", "action": "resume"}, "gui")
        self.assertAlmostEqual(self.e.timer_info()["remaining"], 50, places=1)

    def test_reminder_flashes_then_restores(self):
        self.e.handle({"cmd": "face", "mood": "done"}, "gui")
        now = datetime.datetime(2026, 1, 5, 9, 30)  # a Monday
        self.e.settings.patch({"reminders": [{"id": "a", "time": "09:30", "days": [0], "text": "STAND UP",
                                              "seconds": 10, "enabled": True}]})
        self.e.tick(now)
        self.assertIn("reminder", self.e.current["label"])
        self.e.tick(now)  # same minute: must not fire twice
        self.assertEqual(sum(1 for x in self.e.events if x["type"] == "reminder"), 1)
        self.clock.t += 11
        self.e.tick(now)
        self.assertEqual(self.e.current["mood"], "done")

    def test_invalid_input_is_an_error_not_a_crash(self):
        self.assertFalse(self.e.handle({"cmd": "face", "mood": "nope"}, "gui")["ok"])
        self.assertFalse(self.e.handle({"cmd": "frames", "frames": [{"px": [[0, 0, 0]]}]}, "gui")["ok"])
        self.assertFalse(self.e.handle({"cmd": "timer", "action": "pause"}, "gui")["ok"])

    def test_night_brightness(self):
        self.e.settings.patch({"night": {"enabled": True, "start": "22:00", "end": "07:00", "brightness": 10}})
        self.assertEqual(self.e.effective_brightness(datetime.datetime(2026, 1, 1, 23, 0)), 10)
        self.assertEqual(self.e.effective_brightness(datetime.datetime(2026, 1, 1, 12, 0)), 100)

    def test_idle_sleep_only_after_claude_set_the_display(self):
        self.e.settings.patch({"idle_sleep_minutes": 1})
        self.e.handle({"cmd": "mode", "mode": "clock"}, "gui")
        self.clock.t += 120
        self.e.tick()
        self.assertEqual(self.e.current["kind"], "mode")  # the user's clock stays
        self.e.handle({"cmd": "face", "mood": "done"}, "hook")
        self.clock.t += 120
        self.e.tick()
        self.assertEqual(self.e.current["mood"], "sleep")


class ServerTests(unittest.TestCase):
    def setUp(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        self.e = Engine(new_settings(), FakeBox, Clock(), threads=False)
        self.srv = make_server(self.e, "127.0.0.1", self.port)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def req(self, method, path, body=None, headers=None, host=None, custom=True):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        h = {"Content-Type": "application/json"}
        if custom:
            h["X-Divo"] = "1"
        h.update(headers or {})
        c.putrequest(method, path, skip_host=True)
        c.putheader("Host", host or f"127.0.0.1:{self.port}")
        for k, v in h.items():
            c.putheader(k, v)
        data = json.dumps(body).encode() if body is not None else b""
        c.putheader("Content-Length", str(len(data)))
        c.endheaders(data)
        r = c.getresponse()
        raw = r.read()
        return r.status, (json.loads(raw) if r.getheader("Content-Type", "").startswith("application/json") else raw)

    def test_state_ok(self):
        self.assertEqual(self.req("GET", "/api/state")[0], 200)

    def test_rebinding_host_rejected(self):
        self.assertEqual(self.req("GET", "/api/state", host="evil.example")[0], 403)

    def test_foreign_origin_rejected(self):
        self.assertEqual(self.req("POST", "/api/cmd", {"req": {"cmd": "face", "mood": "idle"}},
                                  {"Origin": "https://evil.example"})[0], 403)

    def test_missing_custom_header_rejected(self):
        self.assertEqual(self.req("POST", "/api/cmd", {}, custom=False)[0], 403)

    def test_settings_need_token(self):
        self.assertEqual(self.req("GET", "/api/settings")[0], 403)
        self.assertEqual(self.req("POST", "/api/settings", {"claude": {"enabled": False}})[0], 403)
        st, body = self.req("POST", "/api/settings", {"claude": {"enabled": False}}, {"X-Divo-Token": self.srv.token})
        self.assertEqual(st, 200)
        self.assertFalse(body["claude"]["enabled"])

    def test_gui_source_needs_token_but_mcp_does_not(self):
        r = {"req": {"cmd": "face", "mood": "idle"}}
        self.assertEqual(self.req("POST", "/api/cmd", {**r, "source": "gui"})[0], 403)
        self.assertTrue(self.req("POST", "/api/cmd", {**r, "source": "mcp"})[1]["ok"])
        self.assertEqual(self.req("POST", "/api/cmd", {**r, "source": "system"})[0], 400)

    def test_claude_cannot_pin_over_cmd(self):
        st, body = self.req("POST", "/api/cmd", {"req": {"cmd": "pin", "value": True}, "source": "mcp"})
        self.assertIn("denied", body)
        self.assertFalse(self.e.pinned)

    def test_page_embeds_token(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port)
        c.request("GET", "/")
        r = c.getresponse()
        self.assertEqual(r.status, 200)
        self.assertIn(self.srv.token.encode(), r.read())


if __name__ == "__main__":
    unittest.main()
