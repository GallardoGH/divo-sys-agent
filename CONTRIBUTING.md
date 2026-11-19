# Contributing

Thanks for taking a look. divo-sys is deliberately small: Python standard library only, no build step, no
dependencies. Please keep it that way.

## Get running

```
git clone https://github.com/haithamexe/divo-sys.git
cd divo-sys
python -m unittest discover -s tests      # no speaker, no network needed
python divo.py demo                        # the full panel against a pretend speaker
```

`python divo.py install` builds and installs the real `divo-sys.exe` (Windows), and `python divo.py build-installer`
builds the `divo-sys-setup.exe` that releases ship. The tests build both in a temporary folder and check their name,
icon and windowless start. When a release is published, `.github/workflows/release.yml` builds the installer on a clean
Windows machine and attaches it with a checksum.

`demo` uses its own port (47833) and a temporary settings folder, so it never touches your real setup. Set
`DIVO_DATA` and `DIVO_PORT` to run any other throw-away copy.

## Layout

- `divosys/` the package. `engine.py` is the heart, `policy.py` the permission rules, `scene.py` and `faces.py` the
  drawing, `server.py` and `web/index.html` the panel.
- `tests/` unittest, one file per area. `test_release.py` includes a guard that fails if a personal name, email or
  Bluetooth address is added to the repository.

## Guidelines

- **No dependencies.** If something needs one, it probably does not belong here.
- **Pure where possible.** Rendering (`scene.py`) and permissions (`policy.py`) are pure functions and are tested
  without hardware. Keep new logic testable the same way: pass the clock and the transport in.
- **Tests for behaviour, including the failure.** A bug fix comes with a test that fails without it.
- **Nothing personal in the repo**: no real addresses, names, paths or screenshots of your own setup. Use `demo` for
  screenshots.
- **The hook runs on every tool call.** `hook.py` and `toolinfo.py` must stay tiny and fast, and must never fail or
  block.
- **Security-relevant changes** (anything in `server.py`, `client.py`, subprocess calls, settings parsing) should be
  explained in the pull request. See [docs/security.md](docs/security.md).

## Adding a face

Faces are 16×16 frames built in `divosys/faces.py` (`_build`). Add the mood there, a description in `server.py`
(`MOOD_DESC`) and `mcp_server.py` (`MOOD_HELP`), and a test. Run `python -m divosys.faces` to print them as text.
Avoid unlit (black) cut-outs for happy features: on an orange face they read as a pumpkin.

## Adding a tool picture

Add the art to `GLYPHS` in `faces.py`, map the tool in `toolinfo.tool_kind`, and add its name to `TOOL_NAMES` in
`web/index.html`.

## Code style

Plain, short functions; comments say why, not what; no clever one-liners where a clear loop does the job.
