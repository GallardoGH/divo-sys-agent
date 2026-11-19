"""Claude-brand pixel faces (16x16) and a tiny 3x5 scrolling-text font.

Every mood is a list of (pixels, delay_ms) frames; pixels is 256 (r, g, b) tuples.
"""
import math
import random

BG = (0, 0, 0)
# LED panels wash colour out, so these are pushed to full saturation rather than the
# muted web brand orange (217,119,87).
CORAL = (255, 96, 24)        # Claude orange, LED-vivid
DIM = (150, 50, 8)           # sleeping body
INK = (0, 0, 0)              # eyes / mouth: unlit pixels, maximum contrast
CREAM = (255, 255, 255)      # sparkles, dots, text

Grid = list  # 16 lists of 16 colours


def _blank():
    return [[BG] * 16 for _ in range(16)]


def _put(g, pts, color, dy=0):
    for y, x in pts:
        if 0 <= y + dy < 16 and 0 <= x < 16:
            g[y + dy][x] = color


def _body(color=CORAL, dy=0):
    g = _blank()
    pts = [(2, x) for x in range(2, 14)] + [(10, x) for x in range(2, 14)]
    pts += [(y, x) for y in range(3, 10) for x in range(1, 15)]
    pts += [(y, x) for y in (11, 12) for x in (2, 3, 5, 6, 9, 10, 12, 13)]
    _put(g, pts, color, dy)
    return g


def _flat(g):
    return [c for row in g for c in row]


# ---- features, as (row, col) lists -------------------------------------------------
EYES_OPEN = [(y, x) for y in (5, 6) for x in (4, 5, 10, 11)]
EYES_BLINK = [(6, x) for x in (4, 5, 10, 11)]
EYES_UP_RIGHT = [(y, x) for y in (4, 5) for x in (5, 6, 11, 12)]
EYES_DOWN_L = [(y, x) for y in (6, 7) for x in (3, 4, 9, 10)]
EYES_DOWN_R = [(y, x) for y in (6, 7) for x in (5, 6, 11, 12)]
EYES_HAPPY = [(5, 5), (5, 6), (6, 4), (6, 7), (5, 10), (5, 11), (6, 9), (6, 12)]
EYES_X = [(5, 4), (5, 6), (6, 5), (7, 4), (7, 6), (5, 10), (5, 12), (6, 11), (7, 10), (7, 12)]
EYES_WIDE = [(y, x) for y in (4, 5, 6) for x in (4, 5, 10, 11)]
MOUTH_SMILE = [(8, 5), (8, 10), (9, 6), (9, 7), (9, 8), (9, 9)]
MOUTH_FLAT = [(9, x) for x in (6, 7, 8, 9)]
MOUTH_O = [(8, 7), (8, 8), (9, 7), (9, 8)]


def _face(eyes, mouth=(), extra=(), extra_color=CREAM, body=CORAL, dy=0, ink=INK):
    g = _body(body, dy)
    _put(g, eyes, ink, dy)
    _put(g, mouth, ink, dy)
    _put(g, extra, extra_color)
    return _flat(g)


def _splash():
    g = _blank()
    c = 7.5
    for y in range(16):
        for x in range(16):
            dx, dy = abs(x - c), abs(y - c)
            r = math.hypot(dx, dy)
            on = (dx < 1.0 or dy < 1.0 or abs(dx - dy) < 0.9) and r < 7.6
            if r < 2.2:
                on = True
            if on:
                g[y][x] = CORAL
    return _flat(g)


def _z(size):
    if size == 1:
        return [(1, 14)]
    return [(0, 12), (0, 13), (0, 14), (1, 13), (2, 12), (2, 13), (2, 14)]


SWEAT = (0, 170, 255)
CONFETTI = [CORAL, CREAM, (0, 200, 255), (255, 60, 200), (255, 230, 0), (0, 255, 100)]


def glitch(pixels, variant=1):
    """Shift some rows sideways (wrapping) to fake a signal glitch."""
    shifts = {1: {4: 3, 5: 3, 9: -2, 11: 2}, 2: {3: -2, 6: 4, 7: 4, 10: -3}}[variant]
    rows = [list(pixels[y * 16:(y + 1) * 16]) for y in range(16)]
    for y, dx in shifts.items():
        rows[y] = rows[y][-dx:] + rows[y][:-dx] if dx else rows[y]
    return [c for r in rows for c in r]


def confetti(pixels, seed, n=26):
    """Sprinkle coloured pixels onto the empty (black) background."""
    rnd = random.Random(seed)
    g = list(pixels)
    placed = 0
    while placed < n:
        i = rnd.randrange(256)
        if g[i] == BG:
            g[i] = rnd.choice(CONFETTI)
            placed += 1
    return g


CHEER_UP = [(2, 0), (3, 0), (2, 15), (3, 15)]      # arms raised
CHEER_DOWN = [(4, 0), (5, 0), (4, 15), (5, 15)]    # arms lowered


def _cheer(arms, sparks=(), eyes=EYES_OPEN, extra=()):
    """The calm face with arms (body colour) and sparkles (white) added around it."""
    g = _body()
    _put(g, eyes, INK)
    _put(g, arms, CORAL)
    _put(g, sparks, CREAM)
    for pts, color in extra:
        _put(g, pts, color)
    return _flat(g)


def _party_frame(k):
    """Party hat bobbing, arms bouncing, confetti falling past the face."""
    sx = k % 2  # the hat bobs one pixel sideways
    hat = [([(0, 7 + sx), (0, 8 + sx)], CREAM),
           ([(1, x + sx) for x in (6, 7, 8, 9)], (255, 60, 200)),
           ([(2, x + sx) for x in (5, 6, 7, 8, 9, 10)], (255, 230, 0))]
    px = _cheer(CHEER_UP if k % 2 == 0 else CHEER_DOWN, eyes=EYES_BLINK if k == 5 else EYES_OPEN, extra=hat)
    g = [list(px[y * 16:(y + 1) * 16]) for y in range(16)]
    rnd = random.Random(7)
    for _ in range(34):
        x, y0, color = rnd.randrange(16), rnd.randrange(16), rnd.choice(CONFETTI)
        y = (y0 + 3 * k) % 16  # each frame the confetti is three rows lower
        if g[y][x] == BG:  # it only shows where the face is not
            g[y][x] = color
    return [c for row in g for c in row]


STAR = (255, 210, 0)  # yellow sparkles


def _plus(y, x):
    return [(y, x), (y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)]


# Where the sparkles are on each of the four beats of the hop: big ones as it lands, small ones as it jumps.
_STARS = (_plus(14, 3) + _plus(14, 12) + [(0, 0), (0, 15)],
          [(13, 1), (13, 14), (15, 5), (15, 10), (1, 0), (2, 15)],
          [(14, 3), (15, 12), (13, 0), (13, 15), (0, 0), (0, 15)],
          [(14, 12), (15, 3), (13, 1), (13, 14), (2, 0), (1, 15)])


def _attention_frame(k):
    """The face hops while its arms wave, with yellow sparkles around it. Sparkles only show where the screen is empty."""
    rows = (3, 5, 7, 5)[k % 4]
    hop = (0, 1, 2, 1)[k % 4]
    arms = [(y, x) for y in (rows, rows + 1) for x in (0, 15)]
    px = _face(EYES_WIDE, MOUTH_O, extra=arms, extra_color=CORAL)
    g = [[BG] * 16 for _ in range(16)]
    for y in range(16 - hop):
        g[y] = list(px[(y + hop) * 16:(y + hop + 1) * 16])
    _put(g, [(y, x) for y, x in _STARS[k % 4] if 0 <= y < 16 and 0 <= x < 16 and g[y][x] == BG], STAR)
    return _flat(g)


def _build():
    f = {}
    calm = [(9, 6), (9, 7), (9, 8), (9, 9)]
    f["idle"] = [(_face(EYES_OPEN, calm), 2800), (_face(EYES_BLINK, calm), 140),
                 (_face(EYES_OPEN, calm), 1900), (_face(EYES_BLINK, calm), 140)]
    dots = [(0, 9), (0, 11), (0, 13)]
    f["thinking"] = [(_face(EYES_UP_RIGHT, extra=dots[:k]), 380) for k in (0, 1, 2, 3)]
    f["working"] = [
        (_face(EYES_DOWN_L if k % 2 == 0 else EYES_DOWN_R, [(8, 7), (8, 8)],
               extra=[(14, 3 + 3 * k), (14, 4 + 3 * k)]), 260)
        for k in range(4)
    ]
    # Same calm eyes as idle and no mouth: a carved smile on orange reads as a pumpkin. The cheer is in the arms.
    f["done"] = [(_cheer(CHEER_UP, [(0, 3), (1, 13), (1, 2)]), 420), (_cheer(CHEER_DOWN, [(0, 12), (1, 3), (1, 14)]), 420)]
    f["attention"] = [(_attention_frame(k), 150) for k in range(8)]  # the four-beat hop, twice
    f["error"] = [(_face(EYES_X, MOUTH_FLAT), 700), (glitch(_face(EYES_X, MOUTH_FLAT), 1), 110),
                  (_face(EYES_X, MOUTH_FLAT), 500), (glitch(_face(EYES_X, MOUTH_FLAT), 2), 110)]
    f["party"] = [(_party_frame(k), 170) for k in range(6)]
    wavy = [(9, 5), (9, 6), (8, 7), (8, 8), (9, 9), (9, 10)]
    f["sweat"] = [(_face(EYES_OPEN, wavy, extra=[(3 + 2 * k, 0), (4 + 2 * k, 0), (6 - 2 * k, 15), (7 - 2 * k, 15)],
                         extra_color=SWEAT), 300) for k in range(3)]
    f["sleep"] = [(_face(EYES_BLINK, [], extra=_z(k), body=DIM, dy=1), 800) for k in (0, 1, 2)]
    f["splash"] = [(_splash(), 1000)]
    return f


FACES = _build()
MOODS = sorted(FACES)

# ---- 3x5 font ----------------------------------------------------------------------
_G = {
    "A": ".#./#.#/###/#.#/#.#", "B": "##./#.#/##./#.#/##.", "C": ".##/#../#../#../.##",
    "D": "##./#.#/#.#/#.#/##.", "E": "###/#../##./#../###", "F": "###/#../##./#../#..",
    "G": ".##/#../#.#/#.#/.##", "H": "#.#/#.#/###/#.#/#.#", "I": "###/.#./.#./.#./###",
    "J": "..#/..#/..#/#.#/.#.", "K": "#.#/#.#/##./#.#/#.#", "L": "#../#../#../#../###",
    "M": "#.#/###/###/#.#/#.#", "N": "##./#.#/#.#/#.#/#.#", "O": ".#./#.#/#.#/#.#/.#.",
    "P": "##./#.#/##./#../#..", "Q": ".#./#.#/#.#/##./.##", "R": "##./#.#/##./#.#/#.#",
    "S": ".##/#../.#./..#/##.", "T": "###/.#./.#./.#./.#.", "U": "#.#/#.#/#.#/#.#/###",
    "V": "#.#/#.#/#.#/#.#/.#.", "W": "#.#/#.#/###/###/#.#", "X": "#.#/#.#/.#./#.#/#.#",
    "Y": "#.#/#.#/.#./.#./.#.", "Z": "###/..#/.#./#../###",
    "0": "###/#.#/#.#/#.#/###", "1": ".#./##./.#./.#./###", "2": "##./..#/.#./#../###",
    "3": "##./..#/.##/..#/##.", "4": "#.#/#.#/###/..#/..#", "5": "###/#../##./..#/##.",
    "6": ".##/#../###/#.#/###", "7": "###/..#/.#./.#./.#.", "8": "###/#.#/###/#.#/###",
    "9": "###/#.#/###/..#/##.",
    ".": "././././#", "!": "#/#/#/./#",
    "?": "##./..#/.#./.../.#.", ":": "./#/./#/.", "-": ".../.../###/.../...",
    "+": ".../.#./###/.#./...", "/": "..#/..#/.#./#../#..", "_": ".../.../.../.../###",
    ",": "./././#/#", "%": "#.#/..#/.#./#../#.#", "'": "#/#/././.", "(": ".#/#./#./#./.#", ")": "#./.#/.#/.#/#.",
}


def _glyph(ch):
    if ch == " ":
        return ["..", "..", "..", "..", ".."]
    rows = _G.get(ch.upper(), _G["?"]).split("/")
    return rows if len(rows) == 5 else _G["?"].split("/")


def text_frames(text, color=CORAL, step=2, delay=90, max_chars=28):
    """Scrolling text, right to left, vertically centred. Returns frame list."""
    text = text.strip()[:max_chars] or "?"
    cols = []  # each column is a 5-tuple of bools
    for ch in text:
        rows = _glyph(ch)
        for x in range(len(rows[0])):
            cols.append(tuple(rows[y][x] == "#" for y in range(5)))
        cols.append((False,) * 5)
    frames = []
    for off in range(16, -len(cols) - 1, -step):
        g = _blank()
        for i, col in enumerate(cols):
            x = off + i
            if 0 <= x < 16:
                for y in range(5):
                    if col[y]:
                        g[5 + y][x] = color
        frames.append((_flat(g), delay))
    return frames



# ---- live displays: timer and system meter -----------------------------------------
RED = (255, 0, 0)
GREEN = (0, 255, 60)
AMBER = (255, 150, 0)
TRACK = (45, 45, 45)


def _draw_glyph(g, ch, x0, y0, color):
    for y, row in enumerate(_glyph(ch)):
        for x, c in enumerate(row):
            if c == "#" and 0 <= y0 + y < 16 and 0 <= x0 + x < 16:
                g[y0 + y][x0 + x] = color


def timer_frame(remaining, total=None, color=CORAL):
    """Minutes over seconds (3x5 digits), progress bar underneath. total=None: no bar (stopwatch)."""
    remaining = max(0, int(remaining))
    mm, ss = min(remaining // 60, 99), remaining % 60
    g = _blank()
    sec_color = RED if (total and remaining <= 10) else CREAM
    for i, ch in enumerate(f"{mm:02d}"):
        _draw_glyph(g, ch, 4 + 4 * i, 1, color)
    for i, ch in enumerate(f"{ss:02d}"):
        _draw_glyph(g, ch, 4 + 4 * i, 8, sec_color)
    if total:
        filled = round(16 * remaining / total)
        for x in range(16):
            for y in (14, 15):
                g[y][x] = color if x < filled else TRACK
    return _flat(g)


def _level_color(pct):
    return GREEN if pct < 60 else AMBER if pct < 85 else RED


def sysmon_frame(cpu, ram):
    """Two horizontal bars: CPU on top, memory below."""
    g = _blank()
    for top, pct in ((3, cpu), (9, ram)):
        filled = round(16 * max(0, min(100, pct)) / 100)
        for x in range(16):
            for y in range(top, top + 4):
                g[y][x] = _level_color(pct) if x < filled else TRACK
    return _flat(g)


def solid_frame(color):
    return [tuple(color)] * 256



# ---- tool glyphs: what Claude is doing, drawn big -----------------------------------
_PAL = {"O": CORAL, "W": CREAM, "Y": (255, 210, 0), "B": (0, 170, 255), "G": (0, 230, 80), "R": (255, 40, 30)}
GLYPHS = {
    "bash": ["WWWWWWWWWWWW", "W..........W", "W.O........W", "W..O.......W", "W...O......W", "W..O.......W",
             "W.O...OOO..W", "W..........W", "WWWWWWWWWWWW"],
    "edit": ["........OO", ".......OOOO", "......OOOO.", ".....YYYO..", "....YYYY...", "...YYYY....", "..YYYY.....",
             ".WYYY......", "WWW........"],
    "read": [".WWW....WWW.", "WWWWW..WWWWW", "WWWWW..WWWWW", "WWKKW..WWKKW", "WWKKW..WWKKW", ".WWW....WWW."],
    "write": ["WWWWWW..", "W....WW.", "W.OO.W.W", "W....WWW", "W.OOOO.W", "W......W", "W.OOO..W", "W......W", "WWWWWWWW"],
    "search": ["..WWWW......", ".W....W.....", "W......W....", "W......W....", "W......W....", ".W....W.....",
               "..WWWW.W....", "........W...", ".........OO.", "..........OO"],
    "web": ["..BBBBBB..", ".B..BB..B.", "B...BB...B", "BBBBBBBBBB", "B...BB...B", "B...BB...B", "BBBBBBBBBB",
            "B...BB...B", ".B..BB..B.", "..BBBBBB.."],
    "agent": ["...WWWW...", "...WWWW...", "....WW....", "..WWWWWW..", "..WW..WW..", "WWWW..WWWW", "WWWW..WWWW"],
    "test": ["..WWWW..", "...WW...", "...WW...", "..W..W..", ".W....W.", "WGGGGGGW", "WGGGGGGW", ".WWWWWW."],
    "git": ["OO......", "OO..OO..", ".O..OO..", ".O.O....", ".OO.....", ".O......", "OO......", "OO......"],
}
GLYPH_KINDS = sorted(GLYPHS)


def glyph_frame(kind):
    """The glyph centred on the screen. Unknown kinds return None."""
    return _art_frame(GLYPHS.get(kind))


def _art_frame(art):
    if not art:
        return None
    g = _blank()
    h, w = len(art), max(len(r) for r in art)
    y0, x0 = (16 - h) // 2, (16 - w) // 2
    for y, row in enumerate(art):
        for x, ch in enumerate(row):
            if ch in _PAL:
                g[y0 + y][x0 + x] = _PAL[ch]
    return _flat(g)



def tests_frame(passed, failed):
    """Big pass count over a green/red bar."""
    g = _blank()
    n = max(0, min(999, passed))
    digits = str(n)
    width = len(digits) * 4 - 1
    for i, ch in enumerate(digits):
        _draw_glyph(g, ch, (16 - width) // 2 + 4 * i, 3, CREAM if failed == 0 else GREEN)
    if failed:
        digits_f = str(min(999, failed))
        wf = len(digits_f) * 4 - 1
        for i, ch in enumerate(digits_f):
            _draw_glyph(g, ch, (16 - wf) // 2 + 4 * i, 9, RED)
    total = max(1, passed + failed)
    green = round(16 * passed / total)
    for x in range(16):
        for y in (14, 15):
            g[y][x] = GREEN if x < green else RED
    return _flat(g)



def monitor_frame(states, blink=False):
    """Up to 16 sites as a 4x4 grid of 3x3 blocks: green up, amber slow, red down (blinks), grey unknown."""
    g = _blank()
    for i, st in enumerate(states[:16]):
        color = {"up": GREEN, "slow": AMBER, "down": RED if blink else (110, 0, 0)}.get(st, TRACK)
        x0, y0 = (i % 4) * 4, (i // 4) * 4
        for y in range(3):
            for x in range(3):
                g[y0 + y][x0 + x] = color
    return _flat(g)


def net_frame(samples):
    """Latency graph: one column per probe (newest on the right). Height grows with milliseconds."""
    g = _blank()
    samples = list(samples)[-16:]
    for i, ms in enumerate(samples):
        x = 16 - len(samples) + i
        if ms is None:  # probe failed
            g[15][x] = g[14][x] = RED
            continue
        h = max(1, min(16, round(ms / 12)))
        color = GREEN if ms < 60 else AMBER if ms < 150 else RED
        for y in range(16 - h, 16):
            g[y][x] = color
    return _flat(g)


def storage_frame(battery, charging, disk_used):
    """Battery on top (omitted on desktops), disk usage below. Low battery and full disks turn red."""
    g = _blank()
    rows = []
    if battery is not None:
        rows.append((3, battery, GREEN if charging or battery > 30 else AMBER if battery > 15 else RED))
    rows.append((9 if battery is not None else 6, disk_used, GREEN if disk_used < 75 else AMBER if disk_used < 90 else RED))
    for top, pct, color in rows:
        filled = round(16 * max(0, min(100, pct)) / 100)
        for x in range(16):
            for y in range(top, top + 4):
                g[y][x] = color if x < filled else TRACK
    return _flat(g)


def render_ascii(pixels):
    sym = {BG: ".", CORAL: "O", DIM: "o", CREAM: "*"}  # INK == BG: unlit
    return "\n".join("".join(sym.get(pixels[y * 16 + x], "+") for x in range(16)) for y in range(16))


if __name__ == "__main__":
    for name in MOODS:
        print(f"--- {name} ({len(FACES[name])} frames)")
        print(render_ascii(FACES[name][0][0]))
    print("--- text 'HI'")
    print(render_ascii(text_frames("HI")[8][0]))
