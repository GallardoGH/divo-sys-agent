import contextlib
import http.client
import io
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from divosys import appinstall, cli, launch  # noqa: E402


def fake_app(shebang_line=b"#!pythonw.exe\n"):
    """Stands in for a built app file on any OS: a fake stub, the '#!' line, then a real zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("__main__.py", "print('hi')\n")
        z.writestr("divosys/x.py", "X = 1\n")
    stub = b"MZ" + bytes(range(256)) * 4  # contains no '#!'
    path = Path(tempfile.mkdtemp()) / "setup.exe"
    path.write_bytes(stub + shebang_line + buf.getvalue())
    return path, stub, buf.getvalue()


class RewriteShebang(unittest.TestCase):
    def test_splits_the_stub_from_the_program(self):
        path, stub, program = fake_app()
        got_stub, got_program = appinstall.split_app(path)
        self.assertEqual(got_stub, stub)
        self.assertEqual(got_program, program)

    def test_only_the_python_changes(self):
        path, stub, program = fake_app()
        out = appinstall.rewrite_shebang(path, path.with_name("app.exe"), "C:/Program Files/Py/pythonw.exe")
        data = out.read_bytes()
        self.assertEqual(data, stub + b'#!"C:/Program Files/Py/pythonw.exe"\n' + program)
        with zipfile.ZipFile(out) as z:  # still a valid program
            self.assertEqual(sorted(z.namelist()), ["__main__.py", "divosys/x.py"])
        again = appinstall.rewrite_shebang(out, out.with_name("again.exe"), "C:/A/pythonw.exe")  # and repeatable
        self.assertEqual(again.read_bytes(), stub + b"#!C:/A/pythonw.exe\n" + program)

    def test_the_source_file_is_left_alone(self):
        path, _, _ = fake_app()
        before = path.read_bytes()
        appinstall.rewrite_shebang(path, path.with_name("app.exe"), "C:/A/pythonw.exe")
        self.assertEqual(path.read_bytes(), before)


class DoubleClick(unittest.TestCase):
    def run_interactive(self, *, installed, running_from_install, accept=True, setup_code=0):
        installed_exe = Path("C:/Profiles/u/divo-sys/divo-sys.exe")
        here = installed_exe if running_from_install else Path("C:/Downloads/divo-sys-setup.exe")
        asked, shown, panel, ran = [], [], [], []

        def fake_setup(say=print, **kw):
            ran.append(True)
            say("  app: installed")
            return setup_code
        with mock.patch.object(launch, "installed", return_value=installed), \
                mock.patch.object(launch, "install_exe", return_value=installed_exe), \
                mock.patch.object(launch, "archive_path", return_value=here), \
                mock.patch("divosys.setup_cmd.setup", fake_setup):
            code = cli.interactive(ask=lambda t: asked.append(t) or accept, show=shown.append,
                                   open_panel=lambda: panel.append(True))
        return code, asked, shown, panel, ran

    def test_the_installed_app_just_opens_the_panel(self):
        code, asked, shown, panel, ran = self.run_interactive(installed=True, running_from_install=True)
        self.assertEqual((code, asked, shown, panel, ran), (0, [], [], [True], []))

    def test_a_fresh_setup_file_asks_then_installs_then_opens_the_panel(self):
        code, asked, shown, panel, ran = self.run_interactive(installed=False, running_from_install=False)
        self.assertEqual(code, 0)
        self.assertTrue(asked[0].startswith("Install divo-sys"))
        self.assertIn("starts with Windows", asked[0])
        self.assertEqual((ran, panel), ([True], [True]))
        self.assertIn("installed", shown[0])

    def test_declining_does_nothing(self):
        code, asked, shown, panel, ran = self.run_interactive(installed=False, running_from_install=False, accept=False)
        self.assertEqual((code, shown, panel, ran), (0, [], [], []))

    def test_a_newer_setup_file_offers_an_update(self):
        _, asked, _, _, ran = self.run_interactive(installed=True, running_from_install=False)
        self.assertTrue(asked[0].startswith("Update divo-sys"))
        self.assertEqual(ran, [True])

    def test_a_failed_setup_is_reported_and_the_panel_is_not_opened(self):
        code, _, shown, panel, _ = self.run_interactive(installed=False, running_from_install=False, setup_code=1)
        self.assertEqual((code, panel), (1, []))
        self.assertTrue(shown)

    @unittest.skipUnless(os.name == "nt", "double-clicking is a Windows thing")
    def test_no_arguments_and_no_console_means_dialogs(self):
        with mock.patch.object(sys, "stdout", None), mock.patch.object(launch, "packed", return_value=True), \
                mock.patch.object(cli, "interactive", return_value=0) as dialogs:
            self.assertEqual(cli.main([]), 0)
        dialogs.assert_called_once()

    def test_no_arguments_with_a_console_prints_the_commands(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main([]), 0)
        self.assertIn("build-installer", out.getvalue())


def stub_available():
    try:
        return os.name == "nt" and appinstall.find_stub().is_file()
    except RuntimeError:
        return False


@unittest.skipUnless(stub_available(), "needs Windows and pip's launcher stub")
class RealInstaller(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix="divo-installer-test-"))
        cls.exe = appinstall.build_installer(cls.work / "divo-sys-setup.exe")

    def test_it_names_itself_as_the_setup_file(self):
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                              f"$v=(Get-Item '{self.exe}').VersionInfo; $v.FileDescription; $v.OriginalFilename"],
                             capture_output=True, text=True, timeout=60).stdout.splitlines()
        self.assertEqual([x.strip() for x in out], ["divo-sys", "divo-sys-setup.exe"])

    def test_it_asks_windows_to_find_python_instead_of_hard_coding_a_path(self):
        stub, program = appinstall.split_app(self.exe)
        self.assertTrue(self.exe.read_bytes().endswith(program))
        self.assertIn(b"#!pythonw.exe\n", self.exe.read_bytes()[len(stub):len(stub) + 40])

    @unittest.skipUnless(shutil.which("pythonw.exe"), "pythonw.exe is not on PATH here")
    def test_it_runs_on_any_pc_that_has_python_on_its_path(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        env = dict(os.environ, DIVO_DEMO="1", DIVO_DATA=str(self.work / "data"), DIVO_PORT=str(port))
        proc = subprocess.Popen([str(self.exe), "daemon"], env=env, creationflags=0x08000000)
        try:
            up = False
            for _ in range(40):
                time.sleep(0.5)
                try:
                    c = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                    c.request("GET", "/api/ping", headers={"X-Divo": "1"})
                    up = c.getresponse().status == 200
                except OSError:
                    continue
                if up:
                    break
            self.assertTrue(up, "the setup file could not find Python on PATH and start")
            token = (self.work / "data" / ".token").read_text(encoding="utf-8").strip()
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            c.request("POST", "/api/quit", "{}", {"X-Divo": "1", "X-Divo-Token": token, "Content-Type": "application/json"})
            c.getresponse().read()
            proc.wait(timeout=15)
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_installing_it_pins_the_python_and_keeps_everything_else(self):
        python = Path(sys.executable).with_name("pythonw.exe")
        installed = appinstall.rewrite_shebang(self.exe, self.work / "installed" / "divo-sys.exe", python)
        self.assertNotEqual(installed.read_bytes(), self.exe.read_bytes())
        self.assertEqual(appinstall.split_app(installed)[0], appinstall.split_app(self.exe)[0])  # same stamped stub
        from divosys import __version__
        done = subprocess.run([str(launch.console_python()), str(installed), "version"], capture_output=True, text=True,
                              timeout=60)
        self.assertEqual(done.stdout.strip(), __version__)

    def test_the_build_installer_command(self):
        out = io.StringIO()
        target = self.work / "cmd-out"
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["build-installer", "--out", str(target)]), 0)
        self.assertTrue((target / "divo-sys-setup.exe").is_file())
        self.assertIn("Python 3.9+", out.getvalue())


if __name__ == "__main__":
    unittest.main()
