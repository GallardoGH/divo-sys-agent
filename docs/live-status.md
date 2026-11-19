# Live status

The hooks report every Claude Code event to the service, which keeps a record of each open session and draws it on
the speaker. The panel's **Live status** page shows the same sessions and controls every option below.

## Sessions

Each Claude Code window is one session. A session is one of:

| State | When |
| --- | --- |
| idle | Just started, nothing yet |
| thinking | You sent a prompt |
| working | A tool is running |
| needs you | A permission prompt or question is waiting on you |
| done | Claude finished its turn |
| asleep | Nothing for 10 minutes (set under Schedule) |

With one session you see its face. With two to four you see a **board**: one 8×8 face each, with a coloured stripe on
top that matches the colour dot in the session list, and a pip along the bottom for the state. More than four show
the four that matter most (waiting on you first, then busiest).

## What gets drawn

| Element | Where | Means |
| --- | --- | --- |
| Tool picture | Alternates with the face while working | The tool in use: terminal, edit, read, write, search, web, sub-agent, tests, git. Each can be switched off |
| Activity heartbeat | Bottom three rows | One column per 5 seconds, a spark for each tool call (taller for more) |
| Sub-agent dots | Top row, left | One per running sub-agent, up to four |
| Build dot | Top right, 2×2 | After a `git push`: amber blinking while the GitHub Actions run for that commit is running, green when it passed (for a minute), red when it failed (until the next push or you dismiss it) |
| Sweat | Replaces the working face | The task has run longer than 3 minutes |
| Elapsed clock | Joins the cycle after 20 s | Minutes over seconds since you sent the prompt. Off by default |
| Hopping, waving arms, yellow sparkles | Replaces the face | Claude is waiting on you |
| Confetti | Brief reaction | A `git push` went through, or tests ran |
| Result frame | Brief reaction | A big pass count over a green/red bar after tests (pytest, unittest, jest/vitest, cargo test). Has its own switch, Test results |
| Glitch | Brief reaction | A tool failed |

## Who wins when several things want the screen

1. **Pin display** (top bar): Claude and the hooks cannot change anything. Your own clicks still work.
2. A **running app** (timer, meters, rotation): live status waits. A waiting-on-you wave still breaks through for a few
   seconds, then the app comes back.
3. A **speaker mode you chose** (clock, light, effects...): live status waits until you press **Resume live status**.
4. A **face or message you or Claude's tools picked**: holds for 30 seconds (configurable), then live status returns.
5. Otherwise live status.

The Dashboard shows a banner when live status is paused, and why.

## Settings (Live status page)

| Setting | Default |
| --- | --- |
| When several sessions are open: board, or only the busiest | board |
| Tool pictures (all, and each one) | on |
| Activity heartbeat | on |
| Sub-agent dots | on |
| Build dot | on |
| Reactions | on |
| Test results | on |
| Elapsed clock | off |
| Start sweating after | 180 s |
| A picked face stays for | 30 s |

On the **Claude** page you can also switch individual faces off (a disabled face is replaced by the calm one), and on
**Schedule** you can set quiet hours, night dimming and the idle-sleep time.

## Events the hooks listen to

`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `Notification` (permission
prompts and questions), `SubagentStart`, `SubagentStop`, `Stop`, `SessionEnd`. The hook sends the tool's name and kind,
the working folder, and, after a test run, a count parsed from the output. The output itself is not kept.
