import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from divosys import icon, setup_cmd  # noqa: E402


def decode_png(data):
    """Minimal reader for the PNGs we write: 8-bit RGBA, filter 0. Returns (width, height, rows of RGBA tuples)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w, h = 8, b"", 0, 0
    while pos < len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        kind, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        assert zlib.crc32(kind + body) & 0xFFFFFFFF == struct.unpack(">I", data[pos + 8 + n:pos + 12 + n])[0]
        if kind == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
            assert body[8:10] == bytes([8, 6])
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    stride = 1 + 4 * w
    rows = []
    for y in range(h):
        line = raw[y * stride:(y + 1) * stride]
        assert line[0] == 0
        rows.append([tuple(line[1 + 4 * x:5 + 4 * x]) for x in range(w)])
    return w, h, rows


class Icon(unittest.TestCase):
    def setUp(self):
        self.data = icon.ico_bytes()
        reserved, kind, count = struct.unpack("<HHH", self.data[:6])
        self.assertEqual((reserved, kind), (0, 1))
        self.entries = [struct.unpack("<BBBBHHII", self.data[6 + 16 * i:22 + 16 * i]) for i in range(count)]

    def test_container_is_consistent(self):
        self.assertEqual(len(self.entries), len(icon.SIZES))
        for (w, h, colors, res, planes, bpp, size, offset), expected in zip(self.entries, icon.SIZES):
            self.assertEqual((w or 256, h or 256), (expected, expected))  # 0 means 256 in an ICO
            self.assertEqual(bpp, 32)
            blob = self.data[offset:offset + size]
            self.assertEqual(len(blob), size)
            pw, ph, rows = decode_png(blob)
            self.assertEqual((pw, ph), (expected, expected))
        last = self.entries[-1]
        self.assertEqual(last[7] + last[6], len(self.data))  # nothing left over

    def test_background_is_transparent_but_the_eyes_are_solid(self):
        w, h, rows = decode_png(self.data[self.entries[-1][7]:self.entries[-1][7] + self.entries[-1][6]])
        self.assertEqual(rows[0][0][3], 0)                 # a corner shows the desktop through
        self.assertEqual(rows[h - 1][w - 1][3], 0)
        eye = rows[5 * 16 + 8][4 * 16 + 8]                  # the face's left eye pupil, at 16x scale
        self.assertEqual(eye, (0, 229, 255, 255))           # ZERO's cyan pupil: opaque, not a hole
        body = rows[8 * 16 + 8][8 * 16 + 8]
        self.assertEqual(body[3], 255)
        self.assertGreater(body[0], 200)                    # Claude orange

    def test_write_icon_creates_the_file(self):
        path = icon.write_icon(Path(tempfile.mkdtemp()) / "sub" / "x.ico")
        self.assertEqual(path.read_bytes(), self.data)


class ShortcutScript(unittest.TestCase):
    def test_quotes_are_doubled_so_odd_paths_cannot_break_out(self):
        self.assertEqual(setup_cmd._ps("it's"), "'it''s'")
        script = setup_cmd.shortcut_script("Desktop", "C:/Program Files/Py/pythonw.exe", '"C:/o\'brien/divo.py" gui',
                                           "C:/o'brien", "C:/o'brien/x.ico", "d")
        self.assertIn("'C:/o''brien/x.ico,0'", script)
        self.assertIn("GetFolderPath('Desktop')", script)
        self.assertIn("divo-sys.lnk", script)
        self.assertIn("$s.Save()", script)

    def test_folder_override_is_used_instead_of_a_windows_folder(self):
        script = setup_cmd.shortcut_script("Desktop", "t", "a", "w", "i", "d", folder="C:/tmp/x")
        self.assertIn("$dir = 'C:/tmp/x'", script)
        self.assertNotIn("GetFolderPath", script)

    def test_unknown_place_is_refused(self):
        if os.name == "nt":
            with self.assertRaises(ValueError):
                setup_cmd.create_shortcut("somewhere-else")
        else:
            with self.assertRaises(RuntimeError):
                setup_cmd.create_shortcut("desktop")


@unittest.skipUnless(os.name == "nt", "shortcuts are a Windows feature")
class RealShortcut(unittest.TestCase):
    def test_creates_a_shortcut_that_opens_the_panel(self):
        folder = tempfile.mkdtemp()
        path = setup_cmd.create_shortcut("desktop", folder=folder)
        self.assertTrue(Path(path).is_file(), path)
        self.assertEqual(Path(path).parent, Path(folder))
        read = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{path}'); "
             "$s.TargetPath; $s.Arguments; $s.WorkingDirectory; $s.IconLocation"],
            capture_output=True, text=True, timeout=30).stdout.splitlines()
        target, args, workdir, icon_loc = (line.strip() for line in read[:4])
        self.assertTrue(target.lower().endswith(("pythonw.exe", "python.exe", "divo-sys.exe")), target)  # no console window
        self.assertTrue(args.endswith("gui"), args)
        self.assertTrue(Path(workdir).is_dir(), workdir)
        self.assertTrue(Path(icon_loc.split(",")[0]).is_file(), icon_loc)


if __name__ == "__main__":
    unittest.main()
