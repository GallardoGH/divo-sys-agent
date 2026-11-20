"""ZERO custom faces (16x16) for the divo-sys fork.

Identity: two 4x4 white eyes with a 2x2 pupil whose COLOUR marks the mood
(cyan calm / amber thinking & attention / red error & anger / green done /
magenta heart & party / blue sweat), plus a mouth below. Special eye modes:
closed lids, happy arches (^ ^), winking lid, magenta hearts. Angry gets
brows; tease gets a tongue; party throws confetti.

Every mood = list of (pixels256, delay_ms). Reverts: delete the override block
at the end of faces.py to bring back the Claude-brand set.
"""
import random

BG = (0, 0, 0)
WHITE = (255, 255, 255)
DIM = (120, 120, 120)
CYAN = (0, 229, 255)
AMBER = (255, 179, 0)
RED = (255, 23, 68)
GREEN = (0, 255, 156)
MAGENTA = (255, 61, 166)
BLUE = (0, 170, 255)

LX, RX, EY, EYE_W = 3, 9, 3, 4    # eye origins and size; mouth band rows 6..9

def _grid():
    return [[BG] * 16 for _ in range(16)]

def _p(g, x, y, c):
    if 0 <= x < 16 and 0 <= y < 16:
        g[y][x] = c

def _eye(g, x0, pupil=CYAN, px=1, py=1, closed=False, arch=False, bar=False, heart=False, lid=False):
    """One 4x4 eye.
    open   : white sclera + 2x2 pupil at (px,py) in 0..2
    closed : DIM horizontal lid (sleep)
    bar    : white top lid half-closed (blink / bored)
    arch   : ^ ^ squint in pupil colour (laughing)
    heart  : 4x4 magenta heart
    lid    : white line only (wink)"""
    if heart:
        for yy, row in enumerate((".#.#.", "#####", "####.", ".##..")):
            for xx, ch in enumerate(row):
                if ch == "#":
                    _p(g, x0 + xx, EY + yy, MAGENTA)
        return
    if arch:
        for xx, yy in ((0, 2), (1, 1), (2, 1), (3, 2)):
            _p(g, x0 + xx, EY + yy, pupil)
        return
    if closed:
        for xx in range(4):
            _p(g, x0 + xx, EY + 1, DIM); _p(g, x0 + xx, EY + 2, DIM)
        return
    if lid or bar:
        for xx in range(4):
            _p(g, x0 + xx, EY, WHITE)
        if not lid:                      # bar keeps a slit of white below
            for xx in range(4):
                _p(g, x0 + xx, EY + 1, WHITE)
        return
    for yy in range(4):
        for xx in range(4):
            _p(g, x0 + xx, EY + yy, WHITE)
    for yy in range(2):
        for xx in range(2):
            _p(g, x0 + px + xx, EY + py + yy, pupil)

def _mouth(g, shape, dy=0):
    y0 = 8 + dy
    pts = []
    if shape == "flat":
        pts = [(y0, x) for x in range(6, 10)]
    elif shape == "small":
        pts = [(y0, x) for x in range(7, 9)]
    elif shape == "smile":
        pts = [(y0 - 1, 5), (y0, 6), (y0, 7), (y0, 8), (y0, 9), (y0 - 1, 10)]
    elif shape == "grin":
        pts = [(y0 - 1, x) for x in range(5, 11)] + [(y0, x) for x in range(4, 12)]
    elif shape == "frown":
        pts = [(y0 + 1, 5), (y0, 6), (y0, 7), (y0, 8), (y0, 9), (y0 + 1, 10)]
    elif shape == "open":
        pts = [(y0 - 1, 7), (y0 - 1, 8), (y0, 6), (y0, 9), (y0 + 1, 7), (y0 + 1, 8)]
    elif shape == "zig":
        pts = [(y0 + (x % 2), x) for x in range(5, 11)]
    elif shape == "wavy":
        pts = [(y0 + (0 if x % 4 < 2 else 1), x) for x in range(5, 11)]
    elif shape == "smirk":
        pts = [(y0 + 1, 5), (y0, 6), (y0, 7), (y0 - 1, 8), (y0 - 1, 9)]
    for y, x in pts:
        _p(g, x, y, WHITE)
    if shape == "tongue":
        for x in range(6, 10):
            _p(g, x, y0 - 1, WHITE)
        for yy in (y0, y0 + 1):
            for xx in (7, 8):
                _p(g, xx, yy, MAGENTA)

def _brow(g, x0, mirror=False):
    for i in range(4):
        _p(g, x0 + i, EY - 2 + (i if not mirror else 3 - i), WHITE)

def E(pupil=CYAN, pl=(1, 1), pr=None, mouth="flat", closed=False, arch=False,
      bar=False, heart=False, closedL=False, lidL=False, brows=0, dy=0, extra=()):
    g = _grid()
    pr = pl if pr is None else pr
    _eye(g, LX, pupil, pl[0], pl[1], closed or closedL, arch, bar, heart, lid=lidL)
    _eye(g, RX, pupil, pr[0], pr[1], closed, arch, bar, heart)
    if brows:
        _brow(g, LX); _brow(g, RX, mirror=True)
    _mouth(g, mouth)
    for x, y, c in extra:
        _p(g, x, y, c)
    if dy:
        out = [[BG] * 16 for _ in range(16)]
        for y in range(16):
            ny = y + dy
            if 0 <= ny < 16:
                out[ny] = g[y]
        g = out
    return [c for r in g for c in r]

def _confetti(seed, n=12, colors=(CYAN, MAGENTA, AMBER, GREEN, WHITE)):
    rnd = random.Random(seed)
    pts = []
    for _ in range(n):
        x = rnd.randrange(16)
        y = rnd.choice((0, 1, 2, 12, 13, 14, 15))
        pts.append((x, y, rnd.choice(colors)))
    return pts

def build():
    f = {}
    f["idle"] = [
        (E(pupil=CYAN, mouth="small"), 2200),
        (E(pupil=CYAN, pl=(0, 1), mouth="small"), 1300),
        (E(pupil=CYAN, pl=(2, 1), mouth="small"), 1300),
        (E(pupil=CYAN, pl=(1, 1), mouth="flat"), 700),
        (E(pupil=CYAN, mouth="small", bar=True), 140),
        (E(pupil=CYAN, mouth="small"), 2400),
    ]
    f["thinking"] = [
        (E(pupil=AMBER, pl=(0, 0), pr=(0, 0), mouth="small"), 620),
        (E(pupil=AMBER, pl=(0, 0), pr=(0, 0), mouth="small"), 480),
        (E(pupil=AMBER, pl=(2, 0), pr=(2, 0), mouth="flat"), 620),
        (E(pupil=AMBER, pl=(2, 0), pr=(2, 0), mouth="small"), 480),
        (E(pupil=AMBER, pl=(1, 0), pr=(1, 0), mouth="small"), 520),
        (E(pupil=AMBER, pl=(1, 2), pr=(1, 2), mouth="open"), 420),
        (E(pupil=AMBER, mouth="small"), 500),
    ]
    scan = [(0, 1), (0, 1), (1, 1), (2, 1), (2, 1), (1, 1)]
    f["working"] = [(E(pupil=CYAN, pl=p, pr=p, mouth="zig"), 250) for p in scan] + [
        (E(pupil=CYAN, mouth="flat", bar=True), 130),
        (E(pupil=CYAN, pl=(0, 1), pr=(0, 1), mouth="zig"), 250),
    ]
    f["done"] = [
        (E(pupil=GREEN, arch=True, mouth="grin"), 320),
        (E(pupil=GREEN, arch=True, mouth="grin", dy=-1), 220),
        (E(pupil=GREEN, arch=True, mouth="smile"), 320),
        (E(pupil=GREEN, arch=True, mouth="grin", dy=-1), 220),
    ] * 2
    f["attention"] = []
    for k in range(8):
        dy = (0, 1, 2, 1)[k % 4]
        spark = [(0, 0, AMBER), (15, 15, AMBER)] if k % 2 else [(0, 15, AMBER), (15, 0, AMBER)]
        f["attention"].append((E(pupil=AMBER, mouth="open", dy=dy, extra=spark), 150))
    f["error"] = [
        (E(pupil=RED, mouth="zig"), 420),
        (E(pupil=RED, mouth="zig", dy=1), 130),
        (E(pupil=RED, pl=(0, 1), pr=(0, 1), mouth="frown"), 420),
        (E(pupil=RED, pl=(2, 1), pr=(2, 1), mouth="frown"), 420),
    ]
    f["sweat"] = []
    for k in range(6):
        d1, d2 = (1 + k) % 16, (8 - k) % 16
        f["sweat"].append((E(pupil=BLUE, pl=(0, 2), pr=(2, 2), mouth="wavy",
                             extra=[(0, d1, BLUE), (15, d2, BLUE)]), 280))
    z1 = [(1, 12, DIM), (2, 13, DIM)]
    z2 = [(0, 12, DIM), (1, 13, DIM), (2, 11, DIM), (2, 12, DIM), (2, 13, DIM)]
    f["sleep"] = [
        (E(closed=True, mouth="small", extra=z1), 900),
        (E(closed=True, mouth="open", extra=z2, dy=1), 1200),
        (E(closed=True, mouth="open", extra=z1, dy=1), 900),
        (E(closed=True, mouth="small", extra=z2), 1000),
    ]
    f["party"] = [(E(pupil=MAGENTA, mouth="grin", dy=0 if k % 2 else 1,
                     extra=_confetti(11 + k)), 180) for k in range(6)]

    g = _grid()
    cx = 7.5
    for y in range(16):
        for x in range(16):
            dx, dy = abs(x - cx), abs(y - cx)
            r = max(dx, dy)
            if r <= 1:
                _p(g, x, y, WHITE)
            elif (dx <= 0.6 or dy <= 0.6 or abs(dx - dy) <= 0.8) and r <= 6:
                _p(g, x, y, CYAN)
    f["splash"] = [([c for row in g for c in row], 1400)]

    # ---- personalidades del fork ---------------------------------------------------
    f["happy"] = [
        (E(pupil=GREEN, arch=True, mouth="grin"), 320),
        (E(pupil=GREEN, arch=True, mouth="grin", dy=-1), 220),
        (E(pupil=GREEN, arch=True, mouth="smile"), 320),
        (E(pupil=GREEN, arch=True, mouth="grin", dy=-1), 220),
    ] * 3
    f["angry"] = [
        (E(pupil=RED, mouth="frown", brows=1), 500),
        (E(pupil=RED, mouth="zig", brows=1, dy=1), 120),
        (E(pupil=RED, mouth="frown", brows=1), 400),
        (E(pupil=RED, pl=(0, 1), pr=(0, 1), mouth="frown", brows=1), 350),
        (E(pupil=RED, mouth="zig", brows=1, dy=1), 120),
        (E(pupil=RED, pl=(2, 1), pr=(2, 1), mouth="frown", brows=1), 450),
    ]
    f["wink"] = [
        (E(pupil=CYAN, lidL=True, pr=(0, 1), mouth="smirk"), 700),
        (E(pupil=CYAN, lidL=True, pr=(2, 0), mouth="smile", dy=-1), 350),
        (E(pupil=CYAN, lidL=True, pr=(0, 1), mouth="smirk"), 700),
        (E(pupil=CYAN, pr=(2, 1), mouth="grin"), 400),
    ]
    f["bored"] = [
        (E(pupil=CYAN, pl=(0, 2), pr=(0, 2), mouth="small"), 800),
        (E(pupil=CYAN, pl=(0, 2), pr=(2, 2), mouth="small"), 650),
        (E(pupil=CYAN, mouth="small", bar=True), 600),
        (E(closed=True, mouth="open", dy=1), 450),
        (E(closed=True, mouth="open", dy=1), 450),
        (E(pupil=CYAN, mouth="small", bar=True), 350),
        (E(pupil=CYAN, pl=(0, 2), pr=(0, 2), mouth="flat"), 700),
    ]
    f["tease"] = [
        (E(pupil=CYAN, pl=(0, 1), pr=(0, 1), mouth="tongue"), 500),
        (E(pupil=CYAN, pl=(2, 1), pr=(2, 1), mouth="tongue", dy=-1), 400),
        (E(pupil=CYAN, pl=(0, 1), pr=(0, 1), mouth="tongue", dy=1), 400),
        (E(pupil=CYAN, mouth="small"), 350),
        (E(pupil=CYAN, pl=(2, 1), pr=(2, 1), mouth="tongue"), 500),
    ]
    f["surprise"] = [
        (E(pupil=CYAN, pl=(1, 0), pr=(1, 0), mouth="small"), 220),
        (E(pupil=CYAN, pl=(1, 0), pr=(1, 0), mouth="open"), 320),
        (E(pupil=CYAN, pl=(1, 0), pr=(1, 0), mouth="open", dy=-1), 420),
        (E(pupil=CYAN, mouth="smile"), 400),
        (E(pupil=CYAN, mouth="grin"), 500),
    ]
    f["heart"] = [
        (E(heart=True, mouth="smile"), 420),
        (E(heart=True, mouth="grin", dy=-1), 300),
        (E(heart=True, mouth="smile"), 420),
    ]
    return f
