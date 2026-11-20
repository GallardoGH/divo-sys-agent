"""ZERO custom faces (16x16): eyes 4x4 with a 2x2 pupil whose colour marks the
mood, plus an expressive mouth below. Replaces the Claude-brand set wholesale.

Every mood is a list of (pixels, delay_ms) frames; pixels = 256 (r, g, b).
Built by tools/divo-panel-es work (fork GallardoGH/divo-sys). To revert: delete
the FACES override at the bottom of faces.py.
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

LX, RX, EY = 3, 9, 3      # left/right eye origin (4x4 box), eye row band 3..6
EYE_W = 4

def _grid():
    return [[BG] * 16 for _ in range(16)]

def _p(g, x, y, c):
    if 0 <= x < 16 and 0 <= y < 16:
        g[y][x] = c

def _eye(g, x0, pupil=CYAN, px=1, py=1, closed=False, arch=False, bar=False):
    """One 4x4 eye. open: white sclera + 2x2 coloured pupil at (px,py) in 0..2.
    closed: horizontal DIM line (sleep). arch: ^ shape (happy squint). bar: white lid line."""
    for yy in range(EYE_W):
        for xx in range(EYE_W):
            if closed and yy in (1, 2):
                _p(g, x0 + xx, EY + yy, DIM)
            elif closed:
                _p(g, x0 + xx, EY + yy, BG)
            elif arch:  # happy squint ^ ^ drawn in the mood's pupil colour
                if (xx, yy) in ((0, 2), (1, 1), (2, 1), (3, 2)):
                    _p(g, x0 + xx, EY + yy, pupil)
            elif bar:
                if yy in (0, 1):
                    _p(g, x0 + xx, EY + yy, WHITE)
            else:
                _p(g, x0 + xx, EY + yy, WHITE)
    if not (closed or arch or bar):
        for yy in range(2):
            for xx in range(2):
                _p(g, x0 + px + xx, EY + py + yy, pupil)

def _mouth(g, shape, dy=0):
    y0 = 8 + dy   # mouth band rows 7..9: centred vertically enough that the icon's middle pixel lands on it
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
    for y, x in pts:
        _p(g, x, y, WHITE)

def _face(pupil=CYAN, pl=(1, 1), pr=None, mouth="flat", closed=False, arch=False,
          bar=False, dy=0, extra=()):
    g = _grid()
    pr = pl if pr is None else pr
    _face_into(g, pupil, pl, pr, mouth, closed, arch, bar, 0, extra)
    if dy:
        out = [[BG] * 16 for _ in range(16)]
        for y in range(16):
            ny = y + dy
            if 0 <= ny < 16:
                out[ny] = g[y]
        g = out
    return [c for r in g for c in r]

def _face_into(g, pupil, pl, pr, mouth, closed, arch, bar, _unused, extra):
    _eye(g, LX, pupil, pl[0], pl[1], closed, arch, bar)
    _eye(g, RX, pupil, pr[0], pr[1], closed, arch, bar)
    _mouth(g, mouth)
    for x, y, c in extra:
        _p(g, x, y, c)

def _flat_shift(pixels, rows):
    out = [list(pixels[y * 16:(y + 1) * 16]) for y in range(16)]
    for y, dx in rows.items():
        out[y] = out[y][-dx:] + out[y][:-dx] if dx else out[y]
    return [c for r in out for c in r]

def _confetti(seed, n=14, colors=(CYAN, MAGENTA, AMBER, GREEN, WHITE)):
    rnd = random.Random(seed)
    pts = []
    placed = 0
    guard = 0
    while placed < n and guard < 400:
        guard += 1
        x, y = rnd.randrange(16), rnd.choice((0, 1, 8, 12, 13, 14, 15))
        pts.append((x, y, rnd.choice(colors)))
        placed += 1
    return pts

def E(**kw):
    return _face(**kw)

def build():
    f = {}
    # idle: ojos cyan centrados, deriva perezosa y parpadeos
    f["idle"] = [
        (E(pupil=CYAN, pl=(1, 1), mouth="small"), 2200),
        (E(pupil=CYAN, pl=(0, 1), mouth="small"), 1300),
        (E(pupil=CYAN, pl=(2, 1), mouth="small"), 1300),
        (E(pupil=CYAN, pl=(1, 1), mouth="flat"), 700),
        (E(pupil=CYAN, mouth="small", bar=True), 140),
        (E(pupil=CYAN, pl=(1, 1), mouth="small"), 2400),
    ]
    # thinking: ambar mirando arriba, va de un lado a otro recordando
    f["thinking"] = [
        (E(pupil=AMBER, pl=(0, 0), pr=(0, 0), mouth="small"), 620),
        (E(pupil=AMBER, pl=(0, 0), pr=(0, 0), mouth="small"), 480),
        (E(pupil=AMBER, pl=(2, 0), pr=(2, 0), mouth="flat"), 620),
        (E(pupil=AMBER, pl=(2, 0), pr=(2, 0), mouth="small"), 480),
        (E(pupil=AMBER, pl=(1, 0), pr=(1, 0), mouth="small"), 520),
        (E(pupil=AMBER, pl=(1, 2), pr=(1, 2), mouth="open"), 420),
        (E(pupil=AMBER, pl=(1, 1), pr=(1, 1), mouth="small"), 500),
    ]
    # working: cyan barre la pantalla, boca apretada, parpadeo al final
    scan = [(0, 1), (0, 1), (1, 1), (2, 1), (2, 1), (1, 1)]
    f["working"] = [(E(pupil=CYAN, pl=p, pr=p, mouth="zig"), 250) for p in scan] + [
        (E(pupil=CYAN, mouth="flat", bar=True), 130),
        (E(pupil=CYAN, pl=(0, 1), pr=(0, 1), mouth="zig"), 250),
    ]
    # done: verde, ojos ^ de risa + rebote y sonrisa amplia
    f["done"] = [
        (E(pupil=GREEN, arch=True, mouth="grin"), 320),
        (E(pupil=GREEN, arch=True, mouth="grin", dy=-1), 200),
        (E(pupil=GREEN, arch=True, mouth="smile"), 320),
        (E(pupil=GREEN, arch=True, mouth="grin", dy=-1), 200),
    ] * 2
    # attention: ambar dilatado, boca O, saltito con destellos
    f["attention"] = []
    for k in range(8):
        dy = (0, 1, 2, 1)[k % 4]
        spark = [(0, 0, AMBER), (15, 15, AMBER)] if k % 2 else [(0, 15, AMBER), (15, 0, AMBER)]
        f["attention"].append((E(pupil=AMBER, mouth="open", dy=dy, extra=spark), 150))
    # error: pupilas rojas, boca de dientes apretados, tembleque y glitch
    f["error"] = [
        (E(pupil=RED, mouth="zig"), 420),
        (E(pupil=RED, mouth="zig", dy=1), 130),
        (_flat_shift(E(pupil=RED, mouth="zig"), {3: 4, 10: -3}), 110),
        (E(pupil=RED, pl=(0, 1), pr=(0, 1), mouth="frown"), 420),
        (E(pupil=RED, pl=(2, 1), pr=(2, 1), mouth="frown"), 420),
        (_flat_shift(E(pupil=RED, mouth="zig"), {4: -3, 11: 4}), 110),
    ]
    # sweat: azul nervioso, boca ondulada, gotas cayendose por los lados
    f["sweat"] = []
    for k in range(6):
        d1, d2 = (1 + k, 2 + k), (8 - k, 7 - k)
        extra = [(0, d1[0] % 16, BLUE), (15, d2[0] % 16, BLUE)]
        f["sweat"].append((E(pupil=BLUE, pl=(0, 2), pr=(2, 2), mouth="wavy", extra=extra), 280))
    # sleep: parpados cerrados, boca O respirando, z arriba a la derecha
    z1 = [(1, 12, DIM), (2, 13, DIM)]
    z2 = [(0, 11, DIM), (0, 12, DIM), (0, 13, DIM), (1, 12, DIM), (2, 11, DIM), (2, 12, DIM), (2, 13, DIM)]
    f["sleep"] = [
        (E(closed=True, mouth="small", extra=z1), 900),
        (E(closed=True, mouth="open", extra=z2, dy=1), 1200),
        (E(closed=True, mouth="open", extra=z2, dy=1), 900),
        (E(closed=True, mouth="small", extra=z1), 1000),
    ]
    # party: magenta con confeti y bote
    f["party"] = []
    for k in range(6):
        f["party"].append((E(pupil=MAGENTA, mouth="grin", dy=0 if k % 2 else 1,
                             extra=_confetti(11 + k)), 180))
    # splash: nuestro estallido de arranque (1 frame, cian/blanco)
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
    return f
