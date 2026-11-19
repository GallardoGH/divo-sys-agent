"""Background watchers: site uptime, GitHub Actions status, weather, network latency.

Everything here is opt-in and runs in the daemon. The only outside services contacted are the sites
you list, GitHub (through your own `gh` login), Open-Meteo for weather, and 1.1.1.1 for the latency graph.
"""
import json
import os
import shutil
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import __version__, protocol

UA = f"divo-sys/{__version__} (local desktop tool)"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


# ---- small network helpers --------------------------------------------------------------
# OpenSSL codes meaning "I can't build the chain to a trusted root with the certificates I have here".
# Windows loads root certificates lazily, so Python can fail where a browser succeeds. The site is still
# answering, so it counts as up. Expired, wrong-host and self-signed certificates are real problems and stay down.
_CHAIN_GAPS = {2, 20, 21}


def check_site(url, timeout=6.0):
    """(up, milliseconds, note). Anything below HTTP 500 counts as up: the server answered."""
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        return False, None, "URL must start with http:// or https://"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    t0 = time.time()
    note = ""
    try:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                r.read(1)
        except urllib.error.URLError as e:
            reason = e.reason
            if isinstance(reason, ssl.SSLCertVerificationError):
                if getattr(reason, "verify_code", None) not in _CHAIN_GAPS:
                    return False, None, f"certificate problem: {getattr(reason, 'verify_message', 'not trusted')}"
                note = "certificate chain not verifiable on this PC"
                with urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as r:
                    r.read(1)
            else:
                raise
        return True, int((time.time() - t0) * 1000), note
    except urllib.error.HTTPError as e:
        return e.code < 500, int((time.time() - t0) * 1000), f"HTTP {e.code}" if e.code >= 500 else note
    except Exception as e:  # DNS, refused, timeout, TLS handshake
        return False, None, f"{type(e).__name__}"


def probe_latency(host="1.1.1.1", port=443, timeout=1.5):
    t0 = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return int((time.time() - t0) * 1000)
    except OSError:
        return None


def http_json(url, timeout=8.0):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def geocode(query):
    """City search through Open-Meteo's geocoding API. Only called when you type a city in the panel."""
    q = urllib.parse.urlencode({"name": query, "count": 5, "language": "en", "format": "json"})
    data = http_json("https://geocoding-api.open-meteo.com/v1/search?" + q)
    return [{"name": r.get("name"), "region": r.get("admin1", ""), "country": r.get("country", ""),
             "lat": r.get("latitude"), "lon": r.get("longitude")} for r in data.get("results", [])]


def wmo_to_weather(code):
    """WMO weather code -> one of the speaker's six skies."""
    if code in (0, 1):
        return "clear"
    if code in (2, 3):
        return "cloudy"
    if code in (45, 48):
        return "fog"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (95, 96, 99):
        return "thunderstorm"
    if code is not None and (51 <= code <= 67 or 80 <= code <= 82):
        return "rain"
    return "cloudy"


def safe_local_dir(path):
    """A real local folder. Network paths (starting with two backslashes or slashes) are refused: simply touching
    one makes Windows open a connection to that machine and send credentials."""
    if not isinstance(path, str) or not path or len(path) > 400:
        return False
    if path.startswith(chr(92) * 2) or path.startswith("//"):
        return False
    return os.path.isabs(path) and os.path.isdir(path)


def valid_sites(items):
    """Only well-formed entries: a dict with a text address. Settings can be edited by hand."""
    out = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and isinstance(it.get("url"), str) and it["url"].strip() and it.get("enabled", True):
            url = it["url"].strip()
            out.append({**it, "url": url, "name": str(it.get("name") or url)[:60], "id": str(it.get("id") or url)})
    return out


# ---- uptime monitor ---------------------------------------------------------------------
class UptimeMonitor:
    def __init__(self, engine):
        self.e = engine
        self.lock = threading.Lock()
        self.results = {}  # id -> {name, url, up, ms, error, fails, t}
        self.wake = threading.Event()

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="uptime").start()

    def snapshot(self):
        with self.lock:
            # no URLs here: this feeds an endpoint without a password, and addresses can carry secrets
            return [dict({a: b for a, b in v.items() if a != "url"}, id=k) for k, v in self.results.items()]

    def states(self):
        """One of up/slow/down/unknown per configured site, in settings order."""
        out = []
        with self.lock:
            for it in valid_sites(self.e.settings.snapshot()["monitors"]["items"]):
                r = self.results.get(it["id"])
                if not r or r["up"] is None:
                    out.append("unknown")
                elif r["up"] is False:
                    out.append("down")
                else:
                    out.append("slow" if (r["ms"] or 0) > 2000 else "up")
        return out

    @staticmethod
    def _interval(cfg):
        try:
            return max(10, min(3600, int(cfg["interval_s"])))
        except (TypeError, ValueError, OverflowError, KeyError):
            return 30

    def _one(self, item):
        up, ms, err = check_site(item["url"])
        iid = item["id"]
        event = None
        with self.lock:
            r = self.results.setdefault(iid, {"up": None, "fails": 0})
            r.update(name=item.get("name") or item["url"], url=item["url"], ms=ms, error=err, t=time.time())
            if up:
                was = r["up"]
                r["fails"], r["up"] = 0, True
                if was is False:
                    event = True
            else:
                r["fails"] += 1
                if r["fails"] >= 2 and r["up"] is not False:  # two misses in a row, so one blip is ignored
                    r["up"] = False
                    event = False
        if event is not None:
            self.e.monitor_event(r["name"], event)

    def _loop(self):
        while not self.e.quit.is_set():
            cfg = self.e.settings.snapshot()["monitors"]
            items = valid_sites(cfg["items"])
            with self.lock:
                keep = {i["id"] for i in items}
                for k in [k for k in self.results if k not in keep]:
                    del self.results[k]
            if items:
                try:
                    with ThreadPoolExecutor(max_workers=8) as ex:
                        list(ex.map(self._one, items))
                except Exception:
                    pass
            self.wake.wait(self._interval(cfg))
            self.wake.clear()


# ---- GitHub Actions watcher -------------------------------------------------------------
def _run(args, cwd, timeout=20):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW)


class CiWatcher:
    """After a `git push`, follow the Actions run for that exact commit until it finishes."""

    def __init__(self, engine):
        self.e = engine
        self.token = 0
        self._last_start = 0.0

    def watch(self, cwd):
        if not safe_local_dir(cwd) or not shutil.which("gh") or not shutil.which("git"):
            return
        if time.time() - self._last_start < 10:  # a flood of push events must not spawn a flood of processes
            return
        self._last_start = time.time()
        self.token += 1
        threading.Thread(target=self._run, args=(cwd, self.token), daemon=True, name="ci").start()

    def _run(self, cwd, token):
        try:
            # fsmonitor is how a booby-trapped repository config can make git run a program; turn it off
            git = ["git", "-c", "core.fsmonitor=false"]
            sha = _run(git + ["rev-parse", "HEAD"], cwd).stdout.strip()
            branch = _run(git + ["rev-parse", "--abbrev-ref", "HEAD"], cwd).stdout.strip()
            repo = os.path.basename(os.path.abspath(cwd))
            if not sha or not branch:
                return
            info = {"state": "waiting", "repo": repo, "branch": branch, "sha": sha[:7], "since": time.time(), "url": ""}
            self.e.ci_update(info)
            started, found = time.time(), False
            while token == self.token and not self.e.quit.is_set() and time.time() - started < 1200:
                r = _run(["gh", "run", "list", "--branch", branch, "--limit", "10",
                          "--json", "headSha,status,conclusion,url"], cwd)
                run = next((x for x in json.loads(r.stdout or "[]") if x.get("headSha") == sha), None) if r.returncode == 0 else None
                if run:
                    found = True
                    if run["status"] == "completed":
                        ok = run.get("conclusion") == "success"
                        self.e.ci_update({**info, "state": "success" if ok else "failure", "url": run.get("url", ""),
                                          "since": time.time()}, finished=True)
                        return
                    self.e.ci_update({**info, "state": "running", "url": run.get("url", "")})
                elif not found and time.time() - started > 90:  # no workflow for this push
                    self.e.ci_update(None)
                    return
                time.sleep(8)
        except Exception:
            self.e.ci_update(None)


# ---- weather ----------------------------------------------------------------------------
class WeatherPoller:
    def __init__(self, engine):
        self.e = engine
        self.wake = threading.Event()

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="weather").start()

    def fetch(self, lat, lon):
        q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code", "timezone": "auto"})
        cur = http_json("https://api.open-meteo.com/v1/forecast?" + q)["current"]
        return round(cur["temperature_2m"]), cur.get("weather_code")

    def _loop(self):
        while not self.e.quit.is_set():
            w = self.e.settings.snapshot()["weather"]
            if w["enabled"] and (w["lat"] or w["lon"]):
                try:
                    temp, code = self.fetch(w["lat"], w["lon"])
                    self.e.weather_update(temp, wmo_to_weather(code), w["city"])
                except Exception as e:
                    self.e.weather_update(None, None, w["city"], error=type(e).__name__)
            self.wake.wait(1200)
            self.wake.clear()
