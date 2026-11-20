"""Local HTTP server: serves the GUI and a small JSON API. Bound to 127.0.0.1 only.

Because any web page you visit can send requests to localhost, every request must carry the
right Host header, a custom X-Divo header (which browsers will not send cross-site without a
CORS preflight we never answer), and, for anything that changes settings, the per-run token
that only the served GUI page contains.
"""
import json
import pkgutil
import secrets
import socket
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import discover, faces, monitors, protocol, system

from .config import HOST, PORT  # noqa: F401
WEB = Path(__file__).resolve().parent / "web"
HTTP_SOURCES = {"mcp", "hook", "gui"}

MOOD_DESC = {
    "idle": "En calma, parpadeando: no pasa nada",
    "thinking": "Ojos arriba, puntos apareciendo: razonando o planificando",
    "working": "Ojos escaneando con barra de progreso: ejecutando herramientas, editando, construyendo",
    "done": "Feliz con destellos: terminado",
    "attention": "Saltando y saludando, ojos abiertos, destellos amarillos: te necesita",
    "error": "Ojos en X: algo fallo",
    "sleep": "Atenuado, ojos cerrados, z flotando: sesion terminada o inactiva",
    "splash": "La estrella de Claude",
    "party": "Sombrero de fiesta, brazos vitoreando, confeti: celebracion",
    "sweat": "Preocupado con gotas de sudor: una tarea larga sigue en marcha",
}
TOOL_DESC = {
    "set_face": "Mostrar una cara para indicar que esta haciendo Claude",
    "show_text": "Deslizar un mensaje corto de estado",
    "draw_pixels": "Dibuja pixel art o animacion a medida",
    "set_brightness": "Change the screen brightness",
    "set_mode": "Switch clock, light, effects, visualizer, scoreboard, weather, apps",
    "timer": "Start, pause or stop a countdown or stopwatch",
}


def meta():
    return {
        "moods": {m: {"desc": MOOD_DESC.get(m, ""), "frames": [
            {"hex": "".join("%02x%02x%02x" % tuple(p) for p in px), "delay": d} for px, d in faces.FACES[m]]}
            for m in faces.MOODS},
        "tools": TOOL_DESC, "effects": protocol.EFFECTS, "clock_styles": protocol.CLOCK_STYLES,
        "light_types": protocol.LIGHT_TYPES, "visualizer_count": protocol.VISUALIZER_COUNT,
        "weather": list(protocol.WEATHER),
        "glyphs": {k: "".join("%02x%02x%02x" % tuple(p) for p in faces.glyph_frame(k)) for k in faces.GLYPH_KINDS},
    }


class _Server(ThreadingHTTPServer):
    """On Windows the default SO_REUSEADDR lets several processes bind the same port, which silently breaks "one
    service per machine" (the port is the lock). Windows has an exclusive option for exactly this."""

    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_server(engine, host=HOST, port=PORT, on_quit=None):
    token = secrets.token_urlsafe(24)
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    allowed_origins = {f"http://{h}" for h in allowed_hosts}

    class Handler(BaseHTTPRequestHandler):
        server_version = "divo-sys"
        timeout = 10  # a stalled or slow client must not hold a thread forever

        def log_message(self, *a):
            pass

        # -- helpers
        def _send(self, code, obj, ctype="application/json"):
            body = obj if isinstance(obj, bytes) else json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if "text" in ctype or "json" in ctype else ""))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")  # no clickjacking of the panel from another site
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; "
                             "style-src 'unsafe-inline'; img-src data:; connect-src 'self'; base-uri 'none'; "
                             "form-action 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _guard(self):
            if self.headers.get("Host", "") not in allowed_hosts:
                self._send(403, {"error": "bad host"})
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in allowed_origins:
                self._send(403, {"error": "bad origin"})
                return False
            return True

        def _admin(self):
            ok = secrets.compare_digest(self.headers.get("X-Divo-Token", ""), token)
            if not ok:
                self._send(403, {"error": "admin token required"})
            return ok

        def _body(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None
            if n < 0 or n > 2_000_000:
                return None
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return None

        # -- routes
        def do_GET(self):
            if not self._guard():
                return
            path = self.path.split("?")[0]
            if path == "/":
                html = pkgutil.get_data("divosys", "web/index.html").decode("utf-8").replace("__TOKEN__", token)
                return self._send(200, html.encode("utf-8"), "text/html")
            if not self.headers.get("X-Divo") and path.startswith("/api/"):
                return self._send(403, {"error": "missing X-Divo header"})
            if path == "/api/ping":  # cheap liveness check that touches no state
                return self._send(200, {"ok": True})
            if path == "/api/state":
                # peek=1 reads without taking the one-shot notices that belong to the panel
                return self._send(200, engine.state(drain="peek=1" not in self.path.partition("?")[2]))
            if path == "/api/preview":
                return self._send(200, engine.get_preview())
            if path == "/api/meta":
                return self._send(200, meta())
            if path == "/api/claude":  # read-only permission summary, for Claude's own status tool
                s = engine.settings.snapshot()["claude"]
                st = engine.state(drain=False)
                return self._send(200, {"permissions": s, "pinned": st["pinned"], "connected": st["connected"],
                                        "showing": st["current"]["label"]})
            if path == "/api/discover":
                if not self._admin():
                    return
                return self._send(200, {"devices": discover.find_speakers()})
            if path == "/api/geocode":
                if not self._admin():
                    return
                q = urllib.parse.parse_qs(self.path.partition("?")[2]).get("q", [""])[0].strip()
                if len(q) < 2:
                    return self._send(200, {"results": []})
                try:
                    return self._send(200, {"results": monitors.geocode(q)})
                except Exception as e:
                    return self._send(200, {"results": [], "error": type(e).__name__})
            if path == "/api/settings":
                if not self._admin():
                    return
                s = engine.settings.snapshot()
                s["autostart"] = system.autostart_enabled()
                return self._send(200, s)
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._guard():
                return
            if not self.headers.get("X-Divo"):
                return self._send(403, {"error": "missing X-Divo header"})
            path = self.path.split("?")[0]
            body = self._body()
            if not isinstance(body, dict):
                return self._send(400, {"error": "bad json"})
            if path == "/api/cmd":
                source = body.get("source", "mcp")
                if source not in HTTP_SOURCES:
                    return self._send(400, {"error": "bad source"})
                if source == "gui" and not self._admin():
                    return
                return self._send(200, engine.handle(body.get("req") or {}, source))
            if not self._admin():
                return
            if path == "/api/settings":
                before = engine.settings.snapshot()
                after = engine.settings.patch(body)
                if "autostart" in body and (after["autostart"] or system.autostart_enabled()):
                    # asking for it on always rewrites the entry, so a moved or reinstalled program is picked up;
                    # asking for it off only has something to do when it is there. Other saves never reach this.
                    system.set_autostart(after["autostart"])
                if after["device"] != before["device"]:
                    engine.request_reconnect()
                with engine.cv:
                    engine._log("gui", "settings saved")
                    engine.cv.notify_all()
                engine.settings_changed()
                return self._send(200, after)
            if path == "/api/shortcut":
                from . import setup_cmd
                try:
                    return self._send(200, {"ok": True, "path": setup_cmd.create_shortcut(body.get("where", "desktop"))})
                except (RuntimeError, ValueError, OSError) as e:
                    return self._send(200, {"ok": False, "error": str(e)})
            if path == "/api/reconnect":
                engine.request_reconnect()
                return self._send(200, {"ok": True})
            if path == "/api/quit":
                self._send(200, {"ok": True})
                if on_quit:
                    on_quit()
                return
            self._send(404, {"error": "not found"})

    srv = _Server((host, port), Handler)
    srv.daemon_threads = True
    srv.token = token
    return srv
