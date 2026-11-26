"""Panel window launchers: native first, browser app-mode second, default browser last (mocked, no GUI)."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from divosys import panel  # noqa: E402


class OpenPanel(unittest.TestCase):
    def test_native_window_wins(self):
        with mock.patch.object(panel, "_native", return_value=True) as native, \
                mock.patch.object(panel, "_app_mode") as app, mock.patch.object(panel.webbrowser, "open") as web:
            self.assertTrue(panel.open_panel())
        native.assert_called_once()
        app.assert_not_called()
        web.assert_not_called()

    def test_app_mode_is_the_fallback(self):
        with mock.patch.object(panel, "_native", return_value=False), \
                mock.patch.object(panel, "_app_mode", return_value=True) as app, \
                mock.patch.object(panel.webbrowser, "open") as web:
            self.assertTrue(panel.open_panel())
        app.assert_called_once()
        web.assert_not_called()

    def test_default_browser_is_the_last_resort(self):
        with mock.patch.object(panel, "_native", return_value=False), \
                mock.patch.object(panel, "_app_mode", return_value=False), \
                mock.patch.object(panel.webbrowser, "open", return_value=True) as web:
            self.assertTrue(panel.open_panel())
        web.assert_called_once_with(panel._url())

    def test_native_never_runs_off_windows(self):
        """pywebview is only offered on Windows; elsewhere the module must not even try to import it."""
        with mock.patch.dict(os.environ, {}), mock.patch.object(panel.os, "name", "posix"):
            self.assertFalse(panel._native())

    def test_title_and_geometry(self):
        self.assertIn("Panel", panel.TITLE)
        self.assertGreaterEqual(panel.WIDTH, 800)
        self.assertGreaterEqual(panel.HEIGHT, 600)


if __name__ == "__main__":
    unittest.main()
