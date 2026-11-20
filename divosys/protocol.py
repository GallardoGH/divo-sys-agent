"""Divoom Timebox Evo wire protocol over Bluetooth RFCOMM. Standard library only.

Message framing:  01 | length(2, LE) | payload | checksum(2, LE) | 02
The length counts the payload plus the 2 checksum bytes; the checksum is the sum of the
length bytes and payload. Protocol notes: RomRider/node-divoom-timebox-evo (PROTOCOL.md).
"""
import datetime
import socket


def frame(payload: bytes) -> bytes:
    body = (len(payload) + 2).to_bytes(2, "little") + payload
    return b"\x01" + body + (sum(body) & 0xFFFF).to_bytes(2, "little") + b"\x02"


# ---- images and animations -----------------------------------------------------------
def _bits_for(n: int) -> int:
    b = 0
    while (1 << b) < n:
        b += 1
    return max(b, 1)


def _palettize(pixels):
    pal, idx, seen = [], [], {}
    for p in pixels:
        p = tuple(p)
        if p not in seen:
            seen[p] = len(pal)
            pal.append(p)
        idx.append(seen[p])
    return pal, idx


def _pack(pal, idx) -> bytes:
    nb = _bits_for(len(pal))
    acc = 0
    for i, v in enumerate(idx):
        acc |= v << (i * nb)
    return acc.to_bytes((len(idx) * nb + 7) // 8, "little")


def image_packet(pixels) -> bytes:
    """pixels: 256 (r, g, b) tuples, row-major, top-left first."""
    pal, idx = _palettize(pixels)
    rest = b"\x00\x00\x00" + bytes([len(pal) & 0xFF]) + b"".join(bytes(c) for c in pal) + _pack(pal, idx)
    return frame(b"\x44\x00\x0A\x0A\x04\xAA" + (len(rest) + 3).to_bytes(2, "little") + rest)


def animation_packets(frames):
    """frames: list of (256 pixels, delay_ms). Endless loop (command 0x49), sent in 200-byte chunks."""
    data = b""
    for px, delay_ms in frames:
        pal, idx = _palettize(px)
        body = (int(delay_ms) & 0xFFFF).to_bytes(2, "little") + b"\x00" + bytes([len(pal) & 0xFF]) \
            + b"".join(bytes(c) for c in pal) + _pack(pal, idx)
        data += b"\xAA" + (len(body) + 3).to_bytes(2, "little") + body
    total = len(data).to_bytes(2, "little")
    return [frame(b"\x49" + total + bytes([n]) + data[o:o + 200]) for n, o in enumerate(range(0, len(data), 200))]


def display_packets(frames):
    """One frame -> still image, several -> animation."""
    if len(frames) == 1:
        return [image_packet(frames[0][0])]
    return animation_packets(frames)


# ---- settings and device-native modes ------------------------------------------------
def brightness_packet(pct: int) -> bytes:
    return frame(b"\x74" + bytes([max(0, min(100, int(pct)))]))


def _rgb(color):
    return bytes(int(c) & 0xFF for c in color)


CLOCK_STYLES = ["Pantalla completa", "Arcoiris", "Con caja", "Analogico cuadrado", "Pantalla completa negativa", "Analogico redondo"]


def clock_packet(style=0, color=(255, 255, 255), time=True, weather=False, temp=False, calendar=False):
    return frame(b"\x45\x00\x01" + bytes([style, int(time), int(weather), int(temp), int(calendar)]) + _rgb(color))


LIGHT_TYPES = ["Plain color", "Love", "Plants", "No mosquito", "Sleeping"]


def light_packet(color=(255, 255, 255), brightness=100, kind=0, power=True):
    return frame(b"\x45\x01" + _rgb(color) + bytes([max(0, min(100, int(brightness))), kind, int(power)]) + b"\x00\x00\x00")


def cloud_packet():
    return frame(b"\x45\x02")


EFFECTS = ["Sparkles", "Lava", "Vertical rainbow lines", "Drops", "Rainbow swirl", "CMY fade", "Rainbow lava",
           "Pastel patterns", "CMY wave", "Fire", "Countdown", "Pink-blue fade", "Rainbow polygons",
           "Pink-blue wave", "Rainbow cross", "Rainbow shapes"]


def effect_packet(kind: int):
    return frame(b"\x45\x03" + bytes([kind]))


VISUALIZER_COUNT = 11  # indices 0..10; the protocol notes only show them as pictures


def visualizer_packet(kind: int):
    return frame(b"\x45\x04" + bytes([kind]))


def scoreboard_packet(red: int, blue: int):
    r, b = max(0, min(999, int(red))), max(0, min(999, int(blue)))
    return frame(b"\x45\x06\x00" + r.to_bytes(2, "little") + b.to_bytes(2, "little"))


WEATHER = {"clear": 1, "cloudy": 3, "thunderstorm": 5, "rain": 6, "snow": 8, "fog": 9}


def weather_packet(temp_c: int, weather: str = "clear"):
    t = max(-127, min(127, int(temp_c)))
    return frame(b"\x5F" + bytes([t & 0xFF, WEATHER.get(weather, 1)]))


def time_packet(when=None):
    d = when or datetime.datetime.now()
    return frame(b"\x18" + bytes([d.year % 100, d.year // 100, d.month, d.day, d.hour, d.minute, d.second, 0]))


class DemoBox:
    """Stands in for the speaker (DIVO_DEMO=1) so the panel can be tried without the hardware."""

    def __init__(self, address, channel=1, timeout=10):
        self.address, self.channel = address, channel

    def connect(self):
        pass

    def send(self, *packets):
        pass

    def close(self):
        pass


# ---- transport -----------------------------------------------------------------------
class Timebox:
    def __init__(self, address, channel=1, timeout=10):
        self.address, self.channel, self.timeout, self.sock = address, channel, timeout, None

    def connect(self):
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        s.settimeout(self.timeout)
        try:
            s.connect((self.address, self.channel))
        except OSError:
            s.close()
            raise
        self.sock = s

    def send(self, *packets: bytes):
        for p in packets:
            for off in range(0, len(p), 666):  # the device wants chunks of at most 666 bytes
                self.sock.sendall(p[off:off + 666])

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None
