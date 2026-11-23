"""The background process: engine + HTTP server. One instance per machine (the port is the lock)."""
import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

from . import protocol, system
from .engine import Engine
from .server import HOST, PORT, make_server
from .settings import DATA_DIR


def _seed_demo(engine):
    """Sample sessions so the panel shows something worth looking at without a speaker (DIVO_DEMO=1)."""
    engine.settings.patch({"device": {"address": "AA:BB:CC:DD:EE:FF"}})
    sample = [("demo-web", "C:/work/web-app", [("UserPromptSubmit", {}), ("PreToolUse", {"tool": "Edit", "kind": "edit"})]),
              ("demo-api", "C:/work/api-server", [("UserPromptSubmit", {}), ("Notification", {"ntype": "permission_prompt"})]),
              ("demo-docs", "C:/work/docs", [("UserPromptSubmit", {}), ("Stop", {})])]
    for sid, cwd, events in sample:
        for name, extra in events:
            engine.handle({"cmd": "event", "event": name, "session": sid, "cwd": cwd, **extra}, "hook")


def run():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(handlers=[RotatingFileHandler(DATA_DIR / "daemon.log", maxBytes=200_000, backupCount=1,
                                                      encoding="utf-8")],
                        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    demo = bool(os.environ.get("DIVO_DEMO"))
    engine = Engine(transport=protocol.DemoBox if demo else protocol.Timebox)
    if demo:
        _seed_demo(engine)
    stop = threading.Event()
    try:
        server = make_server(engine, HOST, PORT, on_quit=stop.set)
    except OSError:
        sys.exit(0)  # another daemon already owns the port
    fd = os.open(str(DATA_DIR / ".token"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(server.token)
    engine.settings.patch({"autostart": system.autostart_enabled()})
    engine.start()
    if not os.environ.get("DIVO_QUIET_START"):   # fork: evitar splash al reiniciar entre locuciones (carrera splash/repintada)
        engine.handle({"cmd": "face", "mood": "splash"}, "system")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logging.info("daemon started on %s:%s", HOST, PORT)
    try:
        stop.wait()
    finally:
        server.shutdown()
        engine.stop()
        logging.info("daemon stopped")
