"""Renombrado de identidad Claude -> OpenClaw/agente en divo-sys-agent (26-11).

Reemplazos mecanicos, UTF-8 explicito, sin tocar literales con mojibake preexistente.
Clave de settings: "claude" -> "agent" con migracion en Settings.__init__.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def rw(rel, pairs, regexes=()):
    p = ROOT / rel
    t = p.read_text(encoding="utf-8")
    orig = t
    for a, b in pairs:
        t = t.replace(a, b)
    for pat, b in regexes:
        t = re.sub(pat, b, t)
    if t != orig:
        p.write_text(t, encoding="utf-8")
        print(f"  editado {rel}")
        return True
    print(f"  (sin cambios) {rel}")
    return False


# ---------- settings.py: clave "claude" -> "agent" + migracion ----------
rw("divosys/settings.py", [
    ('# What Claude (the MCP tools and the status hooks) is allowed to do.\n        "claude": {',
     '# What the agent (OpenClaw: MCP tools and status hooks) is allowed to do.\n        "agent": {'),
    ("# Claude's live status on the speaker (driven by Claude Code hooks).",
     "# Live status on the speaker (driven by agent lifecycle hooks)."),
])

# ---------- engine.py ----------
rw("divosys/engine.py", [
    ('"claude"]', '"agent"]'),                      # snapshot()["claude"] -> ["agent"]
    ('"Claude needs you"', '"Agent needs you"'),
    ('"Claude \u00b7 reaction"', '"Agent \u00b7 reaction"'),
    ('"Claude\'s live status resumed"', '"Agent live status resumed"'),
    ("# last time Claude changed something", "# last time the agent changed something"),
    ("# Claude Code live status", "# agent live status (OpenClaw)"),
    ("# a display set by you (or Claude's tools) keeps", "# a display set by you (or the agent's tools) keeps"),
    ("# ---- Claude Code live status ---", "# ---- agent live status (OpenClaw) ---"),
    ("# what you (or Claude's tools) put on screen is not stomped", "# what you (or the agent) put on screen is not stomped"),
])

# ---------- policy.py ----------
rw("divosys/policy.py", [
    ('"""What is Claude allowed to do on the speaker?',
     '"""What is the agent allowed to do on the speaker?'),
    ("`mcp` (Claude's tools)\nand `hook` (automatic status from Claude Code events) are restricted by settings[\"claude\"].",
     "`mcp` (the agent's tools)\nand `hook` (automatic status from agent events) are restricted by settings[\"agent\"]."),
    ('"Claude control is switched off"', '"Agent control is switched off"'),
    ('f"\'{cmd}\' is not something Claude may do"', 'f"\'{cmd}\' is not something the agent may do"'),
])

# ---------- server.py ----------
rw("divosys/server.py", [
    ('"Mostrar una cara para indicar que esta haciendo Claude"',
     '"Mostrar una cara para indicar que esta haciendo el agente (OpenClaw)"'),
    ('"splash": "La estrella de Claude"', '"splash": "La estrella de bienvenida"'),
    ('if path == "/api/claude":  # read-only permission summary, for Claude\'s own status tool',
     'if path in ("/api/agent", "/api/claude"):  # read-only permission summary for the agent\'s status tool (old alias)'),
    ('s = engine.settings.snapshot()["claude"]', 's = engine.settings.snapshot()["agent"]'),
    ('"set_face": "Show one of Claude\'s pixel faces', '"set_face": "Show one of the agent\'s pixel faces'),
])

# ---------- mcp_server.py ----------
rw("divosys/mcp_server.py", [
    ('"""MCP server (stdio, hand-rolled JSON-RPC, no SDK) that lets Claude use the Divoom Timebox Evo.',
     '"""MCP server (stdio, hand-rolled JSON-RPC, no SDK) that lets an agent (OpenClaw) use the Divoom Timebox Evo.'),
    ("A denied call is reported back as plain text so Claude can adapt instead of retrying.",
     "A denied call is reported back as plain text so the agent can adapt instead of retrying."),
    ('"splash": "the Claude starburst logo"', '"splash": "the welcome starburst logo"'),
    ('"description": "Show one of Claude\'s pixel faces', '"description": "Show one of the agent\'s pixel faces'),
    ('info = get("/api/claude")', 'info = get("/api/agent")'),
    ('"claude_control_enabled": p["enabled"]', '"agent_control_enabled": p["enabled"]'),
])

# ---------- scene.py ----------
rw("divosys/scene.py", [
    ('"""Claude\'s live status scene:', '"""The agent\'s live status scene:'),
    ('"Claude \u00b7 no sessions"', '"Agent \u00b7 no sessions"'),
    ('f"Claude \u00b7 {len(ordered)} sessions"', 'f"Agent \u00b7 {len(ordered)} sessions"'),
    ("f\"Claude \u00b7 {s['project'] or 'session'} \u00b7 {s['state']}\"",
     "f\"Agent \u00b7 {s['project'] or 'session'} \u00b7 {s['state']}\""),
])

# ---------- toolinfo.py ----------
rw("divosys/toolinfo.py", [
    ('"""Light helpers that classify what Claude is doing.',
     '"""Light helpers that classify what the agent is doing.'),
])

# ---------- hook.py ----------
rw("divosys/hook.py", [
    ('"""Claude Code hook: forward a lifecycle event to the daemon.',
     '"""Agent hook: forward a lifecycle event (Claude-Code-shaped payloads, also reusable by other harnesses) to the daemon.'),
    ("Registered for several events; Claude Code sends the event as JSON on stdin.",
     "Registered for several events; the harness sends the event as JSON on stdin."),
])

# ---------- faces.py ----------
rw("divosys/faces.py", [
    ('"""Claude-brand pixel faces (16x16)', '"""Agent pixel faces (16x16)'),
    ("# ---- tool glyphs: what Claude is doing, drawn big ---", "# ---- tool glyphs: what the agent is doing, drawn big ---"),
])

# ---------- zerofaces.py ----------
rw("divosys/zerofaces.py", [
    ("To revert to the Claude-brand set,", "To revert to the upstream brand set,"),
])

# ---------- cli.py ----------
rw("divosys/cli.py", [
    ("Windows, adds the Claude Code hooks and MCP server and a desktop icon",
     "Windows, adds optional agent hooks, the MCP server and a desktop icon"),
    ("  hook                for Claude Code hooks (reads the event on stdin)",
     "  hook                for agent lifecycle hooks (reads the event on stdin)"),
    ("  gui                 open the control panel (starts the service if needed)",
     "  gui                 open the control panel in its own window (starts the service if needed)"),
    ('It adds the Claude "\n               "Code hooks, an MCP server and a desktop icon.',
     'It adds optional agent "\n               "hooks, an MCP server and a desktop icon.'),
])

# ---------- setup_cmd.py ----------
rw("divosys/setup_cmd.py", [
    ('"""`python divo.py setup` and `uninstall`: wire divo-sys into Windows and Claude Code in one step.',
     '"""`python divo.py setup` and `uninstall`: wire divo-sys into Windows and the coding agent in one step.'),
    ('say("Done. Restart Claude Code so it picks up the hooks and the MCP server, and open the panel with: python divo.py gui")',
     'say("Done. Restart your coding agent so it picks up the hooks and the MCP server, and open the panel with: python divo.py gui")'),
])

# ---------- index.html (es, la principal) ----------
rw("divosys/web/index.html", [
    ('<title>divo-sys</title>', '<title>ZERO EVO · Panel</title>'),
    ('<div class="brand"><i></i>divo-sys</div>', '<div class="brand"><i></i>ZERO EVO Panel</div>'),
    ('id="claudeSwitch"><span></span></span> Claude control', 'id="agentSwitch"><span></span></span> Control del agente'),
    ('<button data-tab="claude">Claude</button>', '<button data-tab="agent">Agente</button>'),
    ('<section id="tab-claude" hidden>', '<section id="tab-agent" hidden>'),
    ('<!-- CLAUDE -->', '<!-- AGENTE -->'),
    ('<h2>Que puede hacer Claude</h2>', '<h2>Que puede hacer el agente</h2>'),
    ('Claude recibe el motivo.', 'el agente recibe el motivo.'),
    ('<b>Control de Claude</b>', '<b>Control del agente</b>'),
    ('aria-label="Control de Claude"', 'aria-label="Control del agente"'),
    ('Claude puede ignorar una pantalla fijada', 'El agente puede ignorar una pantalla fijada'),
    ('Normalmente fijar bloquea a Claude por completo.', 'Normalmente fijar bloquea al agente por completo.'),
    ('Herramientas que Claude puede llamar', 'Herramientas que el agente puede llamar'),
    ('Caras que Claude puede mostrar', 'Caras que el agente puede mostrar'),
    ('Apaga una cara y Claude ya no podra mostrarla', 'Apaga una cara y el agente ya no podra mostrarla'),
    ('Segundos minimos entre los cambios de Claude', 'Segundos minimos entre los cambios del agente'),
    ('Brillo minimo que Claude puede poner', 'Brillo minimo que el agente puede poner'),
    ('Brillo maximo que Claude puede poner', 'Brillo maximo que el agente puede poner'),
    ('<b>Bloquear a Claude en estas horas</b>', '<b>Bloquear al agente en estas horas</b>'),
    ('Caras de Claude</h3>', 'Caras del agente</h3>'),
    ('lo que Claude intento y tus ajustes bloquearon', 'lo que el agente intento y tus ajustes bloquearon'),
    ('lo que hacen tus sesiones de Claude Code. Sigue a los hooks el solo.',
     'lo que hacen tus sesiones del agente (OpenClaw y otros). Sigue a los hooks el solo.'),
    ('Caras que siguen lo que hace Claude Code', 'Caras que siguen lo que hace el agente'),
    ('despues de que Claude ejecute tus tests', 'despues de que el agente ejecute tus tests'),
    ('Una cara que tu o Claude elijais', 'Una cara que tu o el agente elijais'),
    ('Claude is waiting on you.', 'The agent is waiting on you.'),
    ('Si una cara puesta por Claude pasa este tiempo', 'Si una cara puesta por el agente pasa este tiempo'),
    ('se reinicia la proxima vez que Claude o este panel lo necesiten',
     'se reinicia la proxima vez que el agente o este panel lo necesiten'),
    # JS: claves de settings
    ("SETTINGS.claude.tools", "SETTINGS.agent.tools"),
    ("SETTINGS.claude.moods", "SETTINGS.agent.moods"),
    ("$('#claudeSwitch')", "$('#agentSwitch')"),
    ("SETTINGS.claude.enabled", "SETTINGS.agent.enabled"),
    ("saveSettings({ claude: { tools:", "saveSettings({ agent: { tools:"),
    ("saveSettings({ claude: { moods:", "saveSettings({ agent: { moods:"),
    ("saveSettings({ claude: { enabled:", "saveSettings({ agent: { enabled:"),
    ("data-set=\"claude.", "data-set=\"agent."),
    # textos JS
    ('a face you or Claude picked stays for', 'a face you or the agent picked stays for'),
    ('"El estado en vivo de Claude esta en pausa: "', '"El estado en vivo del agente esta en pausa: "'),
    ("'1 Claude session: '", "'1 sesion del agente: '"),
    ("ss.length + ' Claude sessions: '", "ss.length + ' sesiones del agente: '"),
    ("'Todavia no hay sesiones de Claude. Aparecen en cuanto Claude Code trabaja.'",
     "'Todavia no hay sesiones del agente. Aparecen en cuanto OpenClaw (u otro agente) trabaja.'"),
    ("'Nada todavia. Las sesiones aparecen aqui cuando Claude Code ejecuta sus hooks.'",
     "'Nada todavia. Las sesiones aparecen aqui cuando el agente ejecuta sus hooks.'"),
])

# ---------- index.html.en ----------
rw("divosys/web/index.html.en", [
    ('<title>divo-sys</title>', '<title>ZERO EVO · Panel</title>'),
    ('<div class="brand"><i></i>divo-sys</div>', '<div class="brand"><i></i>ZERO EVO Panel</div>'),
    ('id="claudeSwitch"><span></span></span> Claude control', 'id="agentSwitch"><span></span></span> Agent control'),
    ('<button data-tab="claude">Claude</button>', '<button data-tab="agent">Agent</button>'),
    ('<section id="tab-claude" hidden>', '<section id="tab-agent" hidden>'),
    ("SETTINGS.claude.tools", "SETTINGS.agent.tools"),
    ("SETTINGS.claude.moods", "SETTINGS.agent.moods"),
    ("$('#claudeSwitch')", "$('#agentSwitch')"),
    ("SETTINGS.claude.enabled", "SETTINGS.agent.enabled"),
    ('saveSettings({ claude: { tools:', 'saveSettings({ agent: { tools:'),
    ('saveSettings({ claude: { moods:', 'saveSettings({ agent: { moods:'),
    ('saveSettings({ claude: { enabled:', 'saveSettings({ agent: { enabled:'),
    ('data-set="claude.', 'data-set="agent.'),
    ("You can remove it any time", "You can remove it any time"),
])
for rel, pairs in [
    ("divosys/web/index.html.en", [
        ("<h2>What Claude may do</h2>", "<h2>What the agent may do</h2>"),
    ]),
]:
    rw(rel, pairs)

# ---------- tests ----------
for rel in ["tests/test_all.py", "tests/test_persistence.py", "tests/test_app.py"]:
    rw(rel, [('{"claude":', '{"agent":'), ('"claude"]', '"agent"]'), ("'claude'", "'agent'")])

rw("tests/test_live.py", [
    ('"Claude needs you"', '"Agent needs you"'),
    ('"Claude \u00b7 reaction"', '"Agent \u00b7 reaction"'),
])

rw("tests/test_hardening.py", [
    ('self.raw("GET", "/api/claude")', 'self.raw("GET", "/api/agent")'),
    ('self.raw("GET", "/api/claude")[1]', 'self.raw("GET", "/api/agent")[1]'),
])

rw("tests/test_release.py", [
    ('def test_claude_dir_honours_the_environment(self):', 'def test_agent_hook_dir_honours_the_environment(self):'),
])

print("done")
