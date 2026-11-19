"""Regression tests for the problems an independent security review found before the public release."""
import datetime
import http.client
import io
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from divosys import client, hook, mcp_server, monitors  # noqa: E402
from divosys.server import make_server  # noqa: E402
from test_release import new_engine  # noqa: E402

ARABIC_FOLDER = "C:/work/\u0645\u0634\u0631\u0648\u0639"


class Hardening(unittest.TestCase):
    def setUp(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        self.e = new_engine()
        self.srv = make_server(self.e, "127.0.0.1", self.port)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def raw(self, method, path, body=b"", headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        c.putrequest(method, path)
        for k, v in dict({"X-Divo": "1", "X-Divo-Token": self.srv.token}, **(headers or {})).items():
            c.putheader(k, v)
        c.endheaders(body)
        r = c.getresponse()
        data = r.read()
        return r.status, (json.loads(data) if data[:1] in (b"{", b"[") else data)

    def test_absurd_numbers_in_settings_are_ignored(self):
        before = self.e.settings.snapshot()
        for bad in (float("inf"), float("-inf"), float("nan"), 10 ** 30, 1e300):
            self.e.settings.patch({"brightness": bad, "idle_sleep_minutes": bad,
                                   "monitors": {"interval_s": bad}, "scene": {"hold_seconds": bad}})
            now = self.e.settings.snapshot()
            self.assertEqual(now["brightness"], before["brightness"], bad)
            self.assertEqual(now["monitors"]["interval_s"], before["monitors"]["interval_s"], bad)
        self.e.settings.patch({"brightness": 40})
        self.assertEqual(self.e.settings.snapshot()["brightness"], 40)  # sensible values still go through
        self.e.effective_brightness()  # and nothing raises

    def test_hostile_timestamps_cannot_freeze_a_session(self):
        for ts in (float("inf"), float("nan"), 10 ** 400, 9e11, True):
            e = new_engine()
            e.handle({"cmd": "event", "event": "PreToolUse", "session": "a", "ts": ts, "tool": "Bash", "kind": "bash"}, "hook")
            e.clock.t += 1
            e.handle({"cmd": "event", "event": "Stop", "session": "a"}, "hook")
            self.assertEqual(e.sessions["a"]["state"], "done", ts)

    def test_event_fields_are_sanitised(self):
        self.e.handle({"cmd": "event", "event": "PreToolUse", "session": "a", "tool": "x" * 500, "kind": "evil"}, "hook")
        s = self.e.sessions["a"]
        self.assertLessEqual(len(s["tool"]), 40)
        self.assertIsNone(s["kind"])
        r = self.e.handle({"cmd": "event", "event": "PostToolUse", "session": "a", "kind": "test",
                           "tests": [float("inf"), 0]}, "hook")
        self.assertFalse(r["ok"])  # a clean error, not a crash
        self.assertTrue(self.e.handle({"cmd": "event", "event": "Stop", "session": "a"}, "hook")["ok"])

    def test_log_fields_are_short(self):
        self.e.handle({"cmd": "face", "mood": "x" * 100000}, "gui")
        entry = self.e.log[0]
        self.assertLessEqual(len(entry["action"]), 80)
        self.assertLessEqual(len(entry["detail"]), 200)

    def test_peeking_does_not_steal_the_panels_notices(self):
        self.e.events.append({"type": "timer_done", "label": "x"})
        self.assertEqual(self.raw("GET", "/api/state?peek=1")[1]["events"], [{"type": "timer_done", "label": "x"}])
        self.assertEqual(len(self.e.events), 1)              # still there for the panel
        self.assertEqual(len(self.raw("GET", "/api/state")[1]["events"]), 1)
        self.assertEqual(self.e.events, [])                  # the panel took them
        self.e.events.append({"type": "ci", "label": "y"})
        self.raw("GET", "/api/claude")
        self.raw("GET", "/api/ping")
        self.assertEqual(len(self.e.events), 1)              # the status tool and the liveness check leave them alone

    def test_open_state_never_contains_site_addresses(self):
        secret_url = "https://user:secret@a.test/?token=abc"
        self.e.settings.patch({"monitors": {"items": [{"id": "1", "name": "s", "url": secret_url, "enabled": True}]}})
        with self.e.uptime.lock:
            self.e.uptime.results["1"] = {"up": True, "ms": 5, "fails": 0, "name": "s", "url": secret_url, "error": ""}
        self.assertNotIn("secret", json.dumps(self.raw("GET", "/api/state")[1]))
        self.assertNotIn("secret", json.dumps(self.raw("GET", "/api/claude")[1]))

    def test_malformed_requests_are_rejected_cleanly(self):
        self.assertEqual(self.raw("POST", "/api/cmd", b"[]", {"Content-Length": "2"})[0], 400)            # not an object
        self.assertEqual(self.raw("POST", "/api/cmd", b"{}", {"Content-Length": "abc"})[0], 400)          # not a number
        self.assertEqual(self.raw("POST", "/api/cmd", b"{}", {"Content-Length": "-5"})[0], 400)           # negative
        self.assertEqual(self.raw("POST", "/api/cmd", b"{nope", {"Content-Length": "5"})[0], 400)         # not JSON
        self.assertEqual(self.raw("POST", "/api/cmd", b"x" * 10, {"Content-Length": "99999999"})[0], 400)  # too big
        self.assertEqual(self.raw("GET", "/api/state")[0], 200)                                            # still serving

    def test_network_paths_are_not_touched(self):
        unc = chr(92) * 2 + "10.0.0.5" + chr(92) + "share"
        for bad in (unc, "//10.0.0.5/share", "relative/dir", "", None, 5, "x" * 500):
            self.assertFalse(monitors.safe_local_dir(bad), repr(bad)[:40])
        self.assertTrue(monitors.safe_local_dir(tempfile.mkdtemp()))

    def test_push_events_cannot_spawn_a_flood_of_watchers(self):
        watcher = monitors.CiWatcher(self.e)
        started = []
        with mock.patch.object(monitors.shutil, "which", return_value="x"), \
                mock.patch.object(monitors.threading, "Thread", side_effect=lambda **kw: started.append(kw) or mock.Mock()):
            folder = tempfile.mkdtemp()
            for _ in range(5):
                watcher.watch(folder)
            watcher.watch(chr(92) * 2 + "evil" + chr(92) + "share")
        self.assertEqual(len(started), 1)

    def test_odd_reminders_do_not_stall_the_tick(self):
        self.e.settings.patch({"reminders": [{"id": ["not", "hashable"], "time": "09:30", "days": "mon",
                                              "seconds": None, "text": "x"}]})
        self.e.tick(datetime.datetime(2026, 1, 5, 9, 30))  # must not raise

    def test_hook_reads_utf8_whatever_the_console_code_page(self):
        payload = json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "s", "cwd": ARABIC_FOLDER}).encode("utf-8")
        fake = mock.Mock()
        fake.isatty.return_value = False
        fake.buffer = io.BytesIO(payload)
        sent = []
        with mock.patch.object(sys, "stdin", fake), mock.patch.object(client, "send", lambda req, src: sent.append(req)):
            with self.assertRaises(SystemExit):
                hook.run()
        self.assertEqual(sent[0]["cwd"], ARABIC_FOLDER)

    def test_mcp_loop_survives_json_that_is_not_an_object(self):
        out = io.StringIO()
        lines = '[]\n"x"\n5\n{"jsonrpc":"2.0","id":1,"method":"ping"}\n'
        with mock.patch.object(sys, "stdin", io.StringIO(lines)), mock.patch.object(sys, "stdout", out):
            mcp_server.main()
        self.assertEqual(json.loads(out.getvalue())["id"], 1)

    @unittest.skipIf(os.name == "nt", "file modes only mean something on Linux/macOS")
    def test_settings_file_is_private(self):
        self.e.settings.patch({"brightness": 50})
        self.assertEqual(self.e.settings.path.stat().st_mode & 0o777, 0o600)

    def test_bluetooth_worker_comes_back_after_an_unexpected_error(self):
        calls = []
        e = new_engine()

        def boom():
            calls.append(1)
            if len(calls) >= 2:
                e.quit.set()
            raise RuntimeError("unexpected")
        e._bt_session = boom
        e.quit.wait = lambda timeout=None: None  # do not really wait
        e._bt_loop()
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
