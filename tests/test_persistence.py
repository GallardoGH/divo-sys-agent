"""Regression tests for: "my choices were not kept after a restart".

Cause: on Windows several copies of the service could bind the same port, so requests and saves went to whichever
copy answered, each with its own stale idea of the settings.
"""
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from divosys import server  # noqa: E402
from divosys.engine import Engine  # noqa: E402
from divosys.settings import Settings  # noqa: E402
from test_release import FakeBox, new_engine  # noqa: E402

CONTENDER = """
import sys, time
sys.path.insert(0, {root!r})
from divosys.server import make_server
class E: pass
try:
    srv = make_server(E(), "127.0.0.1", {port})
except OSError:
    print("busy")
else:
    print("bound", flush=True)
    time.sleep(4)
"""


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class OneService(unittest.TestCase):
    def test_a_second_server_cannot_take_the_same_port(self):
        port = free_port()
        first = server.make_server(new_engine(), "127.0.0.1", port)
        try:
            with self.assertRaises(OSError):
                server.make_server(new_engine(), "127.0.0.1", port)
        finally:
            first.server_close()

    def test_racing_processes_leave_exactly_one_service(self):
        port = free_port()
        code = CONTENDER.format(root=str(ROOT), port=port)
        procs = [subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True) for _ in range(5)]
        try:
            results = [p.stdout.readline().strip() for p in procs]
        finally:
            for p in procs:
                p.kill()
                p.wait()
                p.stdout.close()
        self.assertEqual(results.count("bound"), 1, results)
        self.assertEqual(results.count("busy"), 4, results)


class StartupEntry(unittest.TestCase):
    def setUp(self):
        self.port = free_port()
        self.engine = new_engine()
        self.srv = server.make_server(self.engine, "127.0.0.1", self.port)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def post_settings(self, body):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        raw = json.dumps(body).encode()
        c.request("POST", "/api/settings", raw, {"X-Divo": "1", "X-Divo-Token": self.srv.token,
                                                  "Content-Type": "application/json", "Content-Length": str(len(raw))})
        r = c.getresponse()
        r.read()
        return r.status

    def test_saving_other_settings_never_touches_the_windows_startup_entry(self):
        with mock.patch.object(server.system, "set_autostart") as setter, \
                mock.patch.object(server.system, "autostart_enabled", return_value=True):
            self.assertEqual(self.post_settings({"brightness": 60}), 200)
            self.assertEqual(self.post_settings({"scene": {"heartbeat": False}}), 200)
        setter.assert_not_called()  # a stale in-memory "off" used to flip the real entry off on any save

    def test_asking_for_it_on_refreshes_the_command_even_if_it_is_already_on(self):
        with mock.patch.object(server.system, "set_autostart") as setter,                 mock.patch.object(server.system, "autostart_enabled", return_value=True):
            self.assertEqual(self.post_settings({"autostart": True}), 200)
        setter.assert_called_once_with(True)  # the entry must point at the program as it is now

    def test_asking_for_it_off_when_it_is_already_off_does_nothing(self):
        with mock.patch.object(server.system, "set_autostart") as setter,                 mock.patch.object(server.system, "autostart_enabled", return_value=False):
            self.assertEqual(self.post_settings({"autostart": False}), 200)
        setter.assert_not_called()

    def test_asking_for_it_does(self):
        with mock.patch.object(server.system, "set_autostart") as setter, \
                mock.patch.object(server.system, "autostart_enabled", return_value=False):
            self.assertEqual(self.post_settings({"autostart": True}), 200)
        setter.assert_called_once_with(True)


class ChoicesSurviveARestart(unittest.TestCase):
    def test_every_kind_of_choice_round_trips(self):
        path = os.path.join(tempfile.mkdtemp(), "s.json")
        a = Settings(path)
        a.patch({"agent": {"override_pin": True, "enabled": False, "tools": {"show_text": False},
                            "moods": {"error": False}, "quiet_hours": {"enabled": True, "start": "22:30"}},
                 "scene": {"heartbeat": False, "elapsed_clock": True, "tool_pictures": {"bash": False}},
                 "night": {"enabled": True, "brightness": 12}, "brightness": 55, "idle_sleep_minutes": 3,
                 "reminders": [{"id": "1", "time": "09:00", "days": [0], "text": "HI", "enabled": True}],
                 "monitors": {"items": [{"id": "1", "name": "s", "url": "https://a.test", "enabled": True}], "alert": False},
                 "weather": {"enabled": True, "city": "Testville", "lat": 1.5, "lon": 2.5},
                 "device": {"address": "AA:BB:CC:DD:EE:FF"}})
        b = Settings(path).snapshot()  # a fresh start reading the same file
        self.assertTrue(b["agent"]["override_pin"])
        self.assertFalse(b["agent"]["enabled"])
        self.assertFalse(b["agent"]["tools"]["show_text"])
        self.assertTrue(b["agent"]["tools"]["set_face"])          # what was not changed stays on
        self.assertFalse(b["agent"]["moods"]["error"])
        self.assertEqual(b["agent"]["quiet_hours"], {"enabled": True, "start": "22:30", "end": "07:00"})
        self.assertFalse(b["scene"]["heartbeat"])
        self.assertTrue(b["scene"]["elapsed_clock"])
        self.assertFalse(b["scene"]["tool_pictures"]["bash"])
        self.assertTrue(b["scene"]["tool_pictures"]["edit"])
        self.assertEqual((b["night"]["enabled"], b["night"]["brightness"]), (True, 12))
        self.assertEqual((b["brightness"], b["idle_sleep_minutes"]), (55, 3))
        self.assertEqual(b["reminders"][0]["text"], "HI")
        self.assertEqual(b["monitors"]["items"][0]["url"], "https://a.test")
        self.assertFalse(b["monitors"]["alert"])
        self.assertEqual(b["weather"]["city"], "Testville")
        self.assertEqual(b["device"]["address"], "AA:BB:CC:DD:EE:FF")

    def test_the_pin_survives_a_restart(self):
        path = os.path.join(tempfile.mkdtemp(), "s.json")
        first = Engine(Settings(path), FakeBox, threads=False)
        self.assertFalse(first.pinned)
        first.handle({"cmd": "pin", "value": True}, "gui")
        second = Engine(Settings(path), FakeBox, threads=False)  # the service restarting
        self.assertTrue(second.pinned)
        self.assertIn("denied", second.handle({"cmd": "face", "mood": "idle"}, "hook"))
        second.handle({"cmd": "pin", "value": False}, "gui")
        self.assertFalse(Engine(Settings(path), FakeBox, threads=False).pinned)


if __name__ == "__main__":
    unittest.main()
