"""ZERO custom faces (16x16) for the divo-sys fork.

Identity: two 6x5 rounded white eyes low on the screen with a 2x2 pupil whose
COLOUR marks the mood (cyan calm / amber thinking & attention / red error &
anger / green done & happy / magenta heart & party / blue sweat), and a mouth
in the rows 11..13 band, well separated from the eyes. Special modes: half
lids (bored/wink), blink line, sleep bar, happy arches, 6x5 hearts.

Every mood = list of (pixels256, delay_ms). To revert to the Claude-brand set,
delete the override block at the end of faces.py.
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

LX, RX, EY = 1, 9, 3          # eye origins: 6 wide, rows 3..7; mouth band 11..13

def _grid():
    return [[BG] * 16 for _ in range(16)]

def _p(g, x, y, c):
    if 0 <= x < 16 and 0 <= y < 16:
        g[y][x] = c

def _eye(g, x0, pupil=CYAN, px=1, py=1, closed=False, arch=False, half=False,
         blink=False, heart=False):
    if heart:
        for yy, row in enumerate(("##..##", "######", "######", ".####.", "..##..")):
            for xx, ch in enumerate(row):
                if ch == "#":
                    _p(g, x0 + xx, EY + yy, MAGENTA)
        return
    if arch:  # ^ ^ laughing squint
        for xx, yy in ((0, 5), (1, 4), (2, 3), (3, 3), (4, 4), (5, 5)):
            _p(g, x0 + xx, EY + yy, pupil)
        return
    if closed:  # sleep: dim lids
        for xx in range(6):
            _p(g, x0 + xx, EY + 2, DIM)
            _p(g, x0 + xx, EY + 3, DIM)
        return
    if blink:  # one white line
        for xx in range(6):
            _p(g, x0 + xx, EY + 3, WHITE)
        return
    for xx in range(1, 5):  # rounded top row
        _p(g, x0 + xx, EY, WHITE)
    for yy in range(1, 5):
        for xx in range(6):
            _p(g, x0 + xx, EY + yy, WHITE)
    if half:  # bored: lid down, the bottom slit keeps a visible pupil
        for xx in range(6):
            _p(g, x0 + xx, EY + 3, WHITE)
            _p(g, x0 + xx, EY + 4, WHITE)
        for xx in range(2):
            _p(g, x0 + 2 + px + xx, EY + 3, pupil)
        return
    for yy in range(2):
        for xx in range(2):
            _p(g, x0 + 2 + px + xx, EY + 1 + py + yy, pupil)

def _mouth(g, shape, dy=0):
    y = 12 + dy
    pts = []
    if shape == "flat":
        pts = [(y, x) for x in range(5, 11)]
    elif shape == "small":
        pts = [(y, x) for x in (7, 8)]
    elif shape == "smile":
        pts = [(y - 1, 4), (y - 1, 11)] + [(y, x) for x in range(5, 11)]
    elif shape == "grin":
        pts = [(y - 1, x) for x in range(5, 11)] + [(y, x) for x in range(4, 12)]
    elif shape == "frown":
        pts = [(y, 4), (y, 11)] + [(y - 1, x) for x in range(5, 11)]
    elif shape == "open":
        pts = [(y - 1, 7), (y - 1, 8), (y, 6), (y, 9), (y + 1, 7), (y + 1, 8)]
    elif shape == "zig":
        pts = [(y - 1 + (x % 2), x) for x in range(4, 12)]
    elif shape == "wavy":
        pts = [(y - (0 if x % 4 < 2 else 1), x) for x in range(5, 11)]
    elif shape == "smirk":
        pts = [(y, 4), (y, 5), (y, 6), (y - 1, 7), (y - 1, 8), (y - 1, 9), (y - 2, 10)]
    for yy, x in pts:
        _p(g, x, yy, WHITE)
    if shape == "tongue":
        _p(g, 7, y + 1, MAGENTA)
        _p(g, 8, y + 1, MAGENTA)

def _brows(g):
    for i in range(6):  # inner ends lower: properly angry
        _p(g, LX + i, EY - 2 + (i // 2), WHITE)
        _p(g, RX + (5 - i), EY - 2 + (i // 2), WHITE)

def E(pupil=CYAN, pl=(1, 1), pr=None, mouth="flat", closed=False, arch=False,
      half=False, blink=False, halfL=False, heart=False, brows=0, dy=0, extra=()):
    g = _grid()
    pr = pl if pr is None else pr
    _eye(g, LX, pupil, pl[0], pl[1], closed, arch, half or halfL, blink, heart)
    _eye(g, RX, pupil, pr[0], pr[1], closed, arch, half, blink, heart)
    if brows:
        _brows(g)
    _mouth(g, mouth)
    for x, yy, c in extra:
        _p(g, x, yy, c)
    if dy:
        out = [[BG] * 16 for _ in range(16)]
        for yy in range(16):
            ny = yy + dy
            if 0 <= ny < 16:
                out[ny] = g[yy]
        g = out
    return [c for row in g for c in row]

def _confetti(seed, n=12, colors=(CYAN, MAGENTA, AMBER, GREEN, WHITE)):
    rnd = random.Random(seed)
    return [(rnd.randrange(16), rnd.choice((0, 1, 14, 15)), rnd.choice(colors)) for _ in range(n)]

def build():
    f = {}
    f["idle"] = [
        (E(pupil=CYAN, mouth="small"), 2200),
        (E(pupil=CYAN, pl=(0, 1), mouth="small"), 1300),
        (E(pupil=CYAN, pl=(2, 1), mouth="small"), 1300),
        (E(pupil=CYAN, pl=(1, 1), mouth="flat"), 700),
        (E(pupil=CYAN, blink=True, mouth="small"), 140),
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
        (E(pupil=CYAN, blink=True, mouth="flat"), 130),
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
    f["sweat"] = [
        (E(pupil=BLUE, pl=(0, 2), pr=(2, 2), mouth="wavy",
           extra=[(0, (1 + k) % 16, BLUE), (15, (10 - k) % 16, BLUE)]), 280)
        for k in range(6)
    ]
    z1 = [(12, 1, DIM), (13, 2, DIM)]
    z2 = [(11, 0, DIM), (12, 1, DIM), (13, 0, DIM), (14, 0, DIM), (13, 2, DIM), (12, 2, DIM)]
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
    for yy in range(16):
        for x in range(16):
            dx, dy = abs(x - cx), abs(yy - cx)
            r = max(dx, dy)
            if r <= 1:
                _p(g, x, yy, WHITE)
            elif (dx <= 0.6 or dy <= 0.6 or abs(dx - dy) <= 0.8) and r <= 6:
                _p(g, x, yy, CYAN)
    f["splash"] = [([c for row in g for c in row], 1400)]

    # ---- extra personalities --------------------------------------------------------
    f["happy"] = f["done"]
    f["angry"] = [
        (E(pupil=RED, mouth="frown", brows=1), 500),
        (E(pupil=RED, mouth="zig", brows=1, dy=1), 120),
        (E(pupil=RED, mouth="frown", brows=1), 400),
        (E(pupil=RED, pl=(0, 1), pr=(0, 1), mouth="frown", brows=1), 350),
        (E(pupil=RED, mouth="zig", brows=1, dy=1), 120),
        (E(pupil=RED, pl=(2, 1), pr=(2, 1), mouth="frown", brows=1), 450),
    ]
    f["wink"] = [
        (E(pupil=CYAN, halfL=True, pr=(0, 1), mouth="smirk"), 700),
        (E(pupil=CYAN, halfL=True, pr=(2, 0), mouth="smile", dy=-1), 350),
        (E(pupil=CYAN, halfL=True, pr=(0, 1), mouth="smirk"), 700),
        (E(pupil=CYAN, pr=(2, 1), mouth="grin"), 400),
    ]
    f["bored"] = [
        (E(pupil=CYAN, pl=(0, 2), pr=(0, 2), half=True, mouth="small"), 800),
        (E(pupil=CYAN, pl=(0, 2), pr=(2, 2), half=True, mouth="small"), 650),
        (E(pupil=CYAN, blink=True, mouth="small"), 600),
        (E(closed=True, mouth="open", dy=1), 450),
        (E(closed=True, mouth="open", dy=1), 450),
        (E(pupil=CYAN, half=True, mouth="small"), 350),
        (E(pupil=CYAN, pl=(0, 2), pr=(0, 2), half=True, mouth="flat"), 700),
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
