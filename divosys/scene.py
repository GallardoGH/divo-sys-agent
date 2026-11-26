"""The agent's live status scene: turns what the sessions are doing into frames. Pure functions, no I/O.

A session is a dict: {id, project, state, kind, tool, task_start, attention_since, agents, beats, color}.
States: idle, thinking, working, attention, done, error, sleep.
"""
from . import faces
from .faces import BG, CORAL, CREAM, DIM, GREEN, INK, RED, TRACK, _flat

ACCENTS = [(0, 200, 255), (0, 255, 100), (255, 230, 0), (255, 60, 200)]  # one per session, for the board
AMBER = (255, 150, 0)
BLUE = (0, 170, 255)
STATE_MOOD = {"thinking": "thinking", "working": "working", "attention": "attention", "done": "done",
              "error": "error", "idle": "idle", "sleep": "sleep"}
HEARTBEAT_BUCKET = 5.0  # seconds per column, 16 columns = the last 80 seconds


def _grid(px):
    return [list(px[y * 16:(y + 1) * 16]) for y in range(16)]


# ---- overlays on a 256-pixel frame -----------------------------------------------------
def heartbeat(px, beats, now):
    """Bottom three rows: one column per 5 s, a spark for each tool call."""
    counts = [0] * 16
    for t in beats:
        i = int((now - t) // HEARTBEAT_BUCKET)
        if 0 <= i < 16:
            counts[15 - i] += 1
    g = _grid(px)
    for x, c in enumerate(counts):
        for y in (13, 14, 15):
            g[y][x] = BG
        g[15][x] = TRACK if c == 0 else CREAM
        for k in range(1, min(3, c)):
            g[15 - k][x] = CREAM if k < 2 else CORAL
    return _flat(g)


def agent_dots(px, n, phase):
    g = _grid(px)
    for k in range(min(4, n)):
        g[0][1 + 2 * k] = CREAM if phase == 0 else (130, 130, 130)
    return _flat(g)


def ci_dot(px, state, phase):
    color = {"running": AMBER if phase == 0 else (90, 55, 0), "waiting": AMBER if phase == 0 else (90, 55, 0),
             "success": GREEN, "failure": RED}.get(state)
    if color is None:
        return px
    g = _grid(px)
    for y in (0, 1):
        for x in (14, 15):
            g[y][x] = color
    return _flat(g)


# ---- single session view -----------------------------------------------------------------
def render_single(s, ctx):
    """Frames for one session. ctx: {now, cfg, moods (dict of allowed), ci (dict or None)}."""
    now, cfg = ctx["now"], ctx["cfg"]
    state = s["state"]
    mood = STATE_MOOD.get(state, "idle")
    busy = state in ("thinking", "working")
    elapsed = now - s["task_start"] if busy and s.get("task_start") else 0
    if busy and elapsed >= cfg["sweat_after_s"]:
        mood = "sweat"
    if not ctx["moods"].get(mood, True):
        mood = "idle" if ctx["moods"].get("idle", True) else mood
    base = [(list(px), d) for px, d in faces.FACES[mood]]

    out = []
    for i, (px, d) in enumerate(base):
        phase = i % 2
        if cfg["heartbeat"] and busy:
            px = heartbeat(px, s.get("beats", []), now)
        if cfg["agent_dots"] and s.get("agents"):
            px = agent_dots(px, s["agents"], phase)
        if cfg["ci_dot"] and ctx.get("ci"):
            px = ci_dot(px, ctx["ci"]["state"], phase)
        out.append((px, d))

    if state == "working" and cfg["glyphs"] and s.get("kind") and cfg.get("tool_pictures", {}).get(s["kind"], True):
        g = faces.glyph_frame(s["kind"])
        if g:
            out.append((g, 700))
    if busy and elapsed >= 20 and cfg.get("elapsed_clock"):
        out.append((faces.timer_frame(int(elapsed), None, CORAL), 900))
    return out


# ---- board view (2 to 4 sessions) ----------------------------------------------------------
def mini_face(state, phase, accent):
    """An 8x8 face: accent stripe on top, state pip at the bottom."""
    g = [[BG] * 8 for _ in range(8)]
    body = DIM if state == "sleep" else CORAL
    for x in range(2, 6):
        g[0][x] = accent
    for y in range(1, 6):
        for x in range(1, 7):
            g[y][x] = body
    g[6][2] = g[6][5] = body
    eyes = {"idle": [(2, 2), (2, 5)], "thinking": [(2, 3), (2, 6)], "sleep": [(3, 2), (3, 3), (3, 5), (3, 6)],
            "done": [(2, 2), (2, 5)], "error": [(2, 2), (3, 2), (2, 5), (3, 5)], "attention": [(2, 2), (3, 2), (2, 5), (3, 5)],
            "working": [(3, 2), (3, 5)] if phase == 0 else [(3, 3), (3, 6)]}.get(state, [(2, 2), (2, 5)])
    for y, x in eyes:
        g[y][x] = INK
    if state == "done":  # arms up
        g[1][0] = g[2][0] = g[1][7] = g[2][7] = CORAL
    if state == "attention":
        g[1 + 2 * phase][0] = g[1 + 2 * phase][7] = CORAL
    pip, xs = None, range(2, 6)
    if state == "working":
        pip, xs = CREAM, range(2 + 2 * phase, 4 + 2 * phase)
    elif state == "thinking":
        pip, xs = BLUE, [2 + phase, 4 + phase]
    elif state == "attention":
        pip = AMBER if phase == 0 else (90, 55, 0)
    elif state == "done":
        pip = GREEN
    elif state == "error":
        pip = RED
    elif state == "idle":
        pip = TRACK
    if pip:
        for x in xs:
            g[7][x] = pip
    return g


def render_board(sessions, ctx):
    """2 frames showing up to four sessions as 8x8 faces."""
    sessions = sessions[:4]
    n = len(sessions)
    spots = {1: [(4, 4)], 2: [(0, 4), (8, 4)], 3: [(0, 0), (8, 0), (0, 8)], 4: [(0, 0), (8, 0), (0, 8), (8, 8)]}[n]
    frames = []
    for phase in (0, 1):
        g = [[BG] * 16 for _ in range(16)]
        for s, (x0, y0) in zip(sessions, spots):
            m = mini_face(s["state"], phase, s["color"])
            for y in range(8):
                for x in range(8):
                    g[y0 + y][x0 + x] = m[y][x]
        px = _flat(g)
        if ctx["cfg"]["ci_dot"] and ctx.get("ci"):
            px = ci_dot(px, ctx["ci"]["state"], phase)
        frames.append((px, 450))
    return frames


def pick_order(sessions):
    """Attention first, then busiest, then most recently active."""
    rank = {"attention": 0, "working": 1, "thinking": 2, "error": 3, "done": 4, "idle": 5, "sleep": 6}
    return sorted(sessions, key=lambda s: (rank.get(s["state"], 9), -s.get("last_event", 0)))


def render(sessions, ctx):
    """(frames, label) for the whole scene."""
    if not sessions:
        return list(faces.FACES["sleep"]), "Agent · no sessions"
    ordered = pick_order(sessions)
    if ctx["cfg"]["mode"] == "auto" and len(ordered) >= 2:
        return render_board(ordered, ctx), f"Agent · {len(ordered)} sessions"
    s = ordered[0]
    label = f"Agent · {s['project'] or 'session'} · {s['state']}"
    if s["state"] == "working" and s.get("tool"):
        label += f" ({s['tool']})"
    return render_single(s, ctx), label
