import datetime
import http.client
import json
import os
import re
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from divosys import config, daemon, discover, monitors, protocol, setup_cmd  # noqa: E402
from divosys.engine import Engine  # noqa: E402
from divosys.server import make_server  # noqa: E402
from divosys.settings import Settings  # noqa: E402


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
    return Engine(Settings(os.path.join(tempfile.mkdtemp(), "s.json")), FakeBox, Clock(), threads=False)


class Discover(unittest.TestCase):
    def test_parses_addresses_and_dedupes(self):
        text = ("TimeBox-Evo-audio|BTHLE\\DEV_0123456789AB\\8&250C2EED&0&0123456789AB\n"
                "TimeBox-Evo-light|BTHENUM\\DEV_0123456789AB\\7&1&0&BLUETOOTHDEVICE_0123456789AB\n"
                "Some Other Thing|USB\\VID_1234\n"
                "Pixoo-Max|BTHLE\\DEV_AABBCCDDEEFF\\x\n")
        found = discover.parse_devices(text)
        self.assertEqual([d["address"] for d in found], ["01:23:45:67:89:AB", "AA:BB:CC:DD:EE:FF"])
        self.assertEqual(found[0]["name"], "TimeBox-Evo")  # the -audio suffix is dropped

    def test_empty_and_garbage(self):
        self.assertEqual(discover.parse_devices(""), [])
        self.assertEqual(discover.parse_devices(None), [])
        self.assertEqual(discover.parse_devices("no separator here\n|\nx|DEV_ZZZ"), [])

    def test_engine_adopts_a_single_speaker_and_ignores_several(self):
        e = new_engine()
        with mock.patch.object(discover, "find_speakers", return_value=[{"name": "TimeBox", "address": "AA:BB:CC:DD:EE:01"}]):
            e._auto_discover()
        self.assertEqual(e.settings.snapshot()["device"]["address"], "AA:BB:CC:DD:EE:01")
        e2 = new_engine()
        two = [{"name": "A", "address": "AA:BB:CC:DD:EE:01"}, {"name": "B", "address": "AA:BB:CC:DD:EE:02"}]
        with mock.patch.object(discover, "find_speakers", return_value=two):
            e2._auto_discover()
        self.assertEqual(e2.settings.snapshot()["device"]["address"], "")  # never guesses between devices

    def test_default_settings_carry_no_address(self):
        self.assertEqual(Settings(os.path.join(tempfile.mkdtemp(), "s.json")).snapshot()["device"]["address"], "")


class SetupHooks(unittest.TestCase):
    def test_merge_keeps_other_hooks_and_is_repeatable(self):
        mine = 'python "/opt/divo/divo.py" hook'
        theirs = {"hooks": [{"type": "command", "command": "echo audit"}]}
        s = {"model": "x", "hooks": {"PreToolUse": [dict(theirs, matcher="Bash")], "Custom": [theirs]}}
        setup_cmd.merge_hooks(s, mine)
        first = json.dumps(s, sort_keys=True)
        setup_cmd.merge_hooks(s, mine)
        self.assertEqual(json.dumps(s, sort_keys=True), first)                 # running setup twice changes nothing
        self.assertEqual(s["model"], "x")
        self.assertEqual(len(s["hooks"]["PreToolUse"]), 2)                      # their entry plus ours
        self.assertIn("Custom", s["hooks"])
        for event in setup_cmd.HOOK_EVENTS:
            self.assertTrue(any(setup_cmd._is_ours(e) for e in s["hooks"][event]), event)
        self.assertEqual(s["hooks"]["PostToolUse"][0]["matcher"], "*")
        self.assertTrue(s["hooks"]["Stop"][0]["hooks"][0]["async"])
        self.assertNotIn("matcher", s["hooks"]["Stop"][0])

    def test_remove_restores_the_original(self):
        original = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo audit"}]}]}}
        s = json.loads(json.dumps(original))
        setup_cmd.merge_hooks(s, 'python "/x y/divo.py" hook')
        self.assertGreater(setup_cmd.remove_hooks(s), 5)
        self.assertEqual(s, original)
        empty = {}
        setup_cmd.merge_hooks(empty)
        setup_cmd.remove_hooks(empty)
        self.assertEqual(empty, {})

    def test_recognises_its_own_entries_wherever_the_project_lives(self):
        for cmd in ('"C:/Python/python.exe" "D:/code/divo-sys/divo.py" hook', 'python /home/u/divo.py hook',
                    '"/usr/bin/python3" "/srv/with space/divo.py" hook'):
            self.assertTrue(setup_cmd._is_ours({"hooks": [{"command": cmd}]}), cmd)
        self.assertFalse(setup_cmd._is_ours({"hooks": [{"command": "python other.py hook"}]}))

    def test_hook_command_is_quoted_for_paths_with_spaces(self):
        cmd = setup_cmd.hook_command()
        self.assertTrue(cmd.startswith('"') and cmd.endswith(" hook"))
        self.assertTrue('divo.py"' in cmd or 'divo-sys.exe"' in cmd, cmd)

    def test_invalid_settings_file_is_never_overwritten(self):
        path = Path(tempfile.mkdtemp()) / "settings.json"
        path.write_text("{ not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            setup_cmd.read_settings(path)
        self.assertEqual(path.read_text(encoding="utf-8"), "{ not json")
        path.write_text("[1, 2]", encoding="utf-8")
        with self.assertRaises(ValueError):
            setup_cmd.read_settings(path)

    def test_backup_is_made_once(self):
        path = Path(tempfile.mkdtemp()) / "settings.json"
        path.write_text('{"a": 1}', encoding="utf-8")
        setup_cmd.write_settings(path, {"a": 2})
        setup_cmd.write_settings(path, {"a": 3})
        backup = path.with_name(path.name + setup_cmd.BACKUP_SUFFIX)
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), {"a": 1})   # the original, not the second save
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"a": 3})

    def test_missing_file_is_an_empty_object(self):
        self.assertEqual(setup_cmd.read_settings(Path(tempfile.mkdtemp()) / "nope.json"), {})

    def test_agent_hook_dir_honours_the_environment(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "/somewhere/else"}):
            self.assertEqual(setup_cmd.claude_dir(), Path("/somewhere/else"))


class Robustness(unittest.TestCase):
    def test_port_comes_from_the_environment_and_is_validated(self):
        with mock.patch.dict(os.environ, {"DIVO_PORT": "50123"}):
            self.assertEqual(config._port(), 50123)
        for bad in ("abc", "80", "99999", ""):
            with mock.patch.dict(os.environ, {"DIVO_PORT": bad}):
                self.assertEqual(config._port(), 47831, bad)

    def test_sessions_are_capped(self):
        e = new_engine()
        for i in range(70):
            e.clock.t += 1
            e.handle({"cmd": "event", "event": "UserPromptSubmit", "session": f"s{i}", "cwd": "C:/x"}, "hook")
        self.assertLessEqual(len(e.sessions), 50)
        self.assertIn("s69", e.sessions)       # the newest survive
        self.assertNotIn("s0", e.sessions)     # the oldest are dropped

    def test_hand_edited_settings_do_not_break_the_tick(self):
        e = new_engine()
        e.settings.patch({"reminders": [{"id": "x", "time": "09:30", "days": [0], "seconds": "abc", "text": "hi"},
                                        "junk", {"time": None}],
                          "rotation": {"items": [{"type": "face", "mood": "idle", "seconds": "soon"}, 5, None]},
                          "monitors": {"items": [None, 5, {"url": 3}, {"url": "   "}, {"id": 1, "url": "https://a.test"}]}})
        e.handle({"cmd": "app", "name": "rotation", "action": "start"}, "gui")
        e.tick(datetime.datetime(2026, 1, 5, 9, 30))  # a Monday: the odd reminder fires, nothing may raise
        self.assertEqual(len(monitors.valid_sites(e.settings.snapshot()["monitors"]["items"])), 1)
        self.assertEqual(e.uptime.states(), ["unknown"])

    def test_valid_sites_normalises(self):
        out = monitors.valid_sites([{"url": " https://a.test ", "name": None, "id": 7}, {"url": "https://b.test", "enabled": False}])
        self.assertEqual(out, [{"url": "https://a.test", "name": "https://a.test", "id": "7"}])
        self.assertEqual(monitors.valid_sites("nonsense"), [])

    def test_demo_mode_seeds_sessions_and_uses_a_pretend_speaker(self):
        e = new_engine()
        daemon._seed_demo(e)
        self.assertEqual(len(e.sessions), 3)
        self.assertEqual({s["state"] for s in e.sessions.values()}, {"working", "attention", "done"})
        self.assertEqual(e.settings.snapshot()["device"]["address"], "AA:BB:CC:DD:EE:FF")
        box = protocol.DemoBox("x")
        box.connect()
        box.send(b"anything")
        box.close()


class Headers(unittest.TestCase):
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

    def get(self, path, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        c.request("GET", path, headers=dict({"X-Divo": "1"}, **(headers or {})))
        r = c.getresponse()
        r.read()
        return r

    def test_security_headers_on_the_page_and_the_api(self):
        for path in ("/", "/api/state"):
            r = self.get(path)
            self.assertEqual(r.getheader("X-Frame-Options"), "DENY", path)
            self.assertIn("frame-ancestors 'none'", r.getheader("Content-Security-Policy"), path)
            self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff", path)
            self.assertEqual(r.getheader("Referrer-Policy"), "no-referrer", path)
            self.assertIn("default-src 'none'", r.getheader("Content-Security-Policy"), path)

    def test_discover_needs_the_token(self):
        self.assertEqual(self.get("/api/discover").status, 403)
        with mock.patch.object(discover, "find_speakers", return_value=[]):
            self.assertEqual(self.get("/api/discover", {"X-Divo-Token": self.srv.token}).status, 200)


class NoPersonalInformation(unittest.TestCase):
    """A guard for a public repository: fail if a real name, email or Bluetooth address creeps back in."""

    # Structural checks, so this file never has to spell out the personal values it guards against.
    EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
    OK_EMAIL_ENDINGS = ("users.noreply.github.com", "example.com", "example.org", ".test", ".invalid")  # .test/.invalid never resolve
    USER_PATH = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s<>\"']+", re.I)
    MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")
    ALLOWED_MACS = {"AA:BB:CC:DD:EE:FF", "AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02", "01:23:45:67:89:AB"}

    def files(self):
        for base in ("divosys", "docs", "tests"):
            for p in (ROOT / base).rglob("*"):
                if p.is_file() and p.suffix in {".py", ".html", ".md", ".yml", ".json", ".txt"} and p.name != "test_release.py":
                    yield p
        for name in ("divo.py", "README.md", "LICENSE", "CONTRIBUTING.md"):
            if (ROOT / name).exists():
                yield ROOT / name

    def test_no_names_emails_or_real_addresses(self):
        for p in self.files():
            text = p.read_text(encoding="utf-8", errors="ignore")
            for email in self.EMAIL.findall(text):
                self.assertTrue(email.lower().endswith(self.OK_EMAIL_ENDINGS), f"{p.relative_to(ROOT)} contains an email address")
            self.assertIsNone(self.USER_PATH.search(text), f"{p.relative_to(ROOT)} contains a Windows user-profile path")
            for mac in self.MAC.findall(text):
                self.assertIn(mac.upper(), self.ALLOWED_MACS, f"{p.relative_to(ROOT)} contains the address {mac}")


if __name__ == "__main__":
    unittest.main()
