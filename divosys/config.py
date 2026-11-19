"""Constants shared by everything, kept import-light so hooks start fast."""
import os
from pathlib import Path


def _port():
    try:
        port = int(os.environ.get("DIVO_PORT", "47831"))
    except ValueError:
        return 47831
    return port if 1024 <= port <= 65535 else 47831


HOST, PORT = "127.0.0.1", _port()
ROOT = Path(__file__).resolve().parent.parent
LEGACY_DATA_DIR = ROOT / "data"  # where a checkout used to keep its settings; read once if there is nothing newer


def _data_dir():
    if os.environ.get("DIVO_DATA"):
        return Path(os.environ["DIVO_DATA"])
    if os.name == "nt":
        from . import launch
        return launch.app_data_dir()
    if (ROOT / "divo.py").is_file():  # a checkout keeps its data beside the code
        return LEGACY_DATA_DIR
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "divo-sys"


DATA_DIR = _data_dir()
