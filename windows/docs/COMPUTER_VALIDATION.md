# Windows Computer Use validation — 2026-10-08

Computer Use runs its own native MCP and Cursor Studio. Browser Use is a separate
repository/MCP. This checkout does not ship or start the Browser extension or a
combined broker. An optional exported character JSON contains presentation only.

Host: Windows, Python 3.13, Cua Driver **0.28.2**. Ordinary unit tests do not
interact with the desktop. Run from `windows/`:

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe scripts/mcp_smoke_windows.py --output artifacts/standalone-mcp.json
```

The unit suite has **250 passes**. The standalone reloadable MCP exposes **69
tools**, preserving all **57 original Cua schemas**. The opt-in smoke only reads
tool schemas and packaged skills. It compares original Cua tool schemas without
modification and checks that no imported Browser tools are exposed; no desktop
observations or input are sent.

## Disposable native fixture

The preceding live check used only `WindowsComputerFixture`, through the opt-in
`scripts/live_acceptance_windows.py`, with no foreground-input flag. Ten executed
checks passed and two foreground fallbacks were skipped. This is separate from
the Browser repository's headless tab tests.

- Covered-window screenshot and native UIA elements were obtained.
- Semantic/pixel click increased the fixture count from zero to two.
- UIA set-value/type changed its field to `Typed in background`; fresh observation
  and fixture events confirmed the text. UIA scroll changed visible rows 00–07
  to 21–28. Foreground window and physical mouse position stayed unchanged.
- Pixel wheel and background drag were explicitly refused on this fixture/driver.
  These checks passed for honest refusal and no automatic foreground escalation,
  not successful delivery. The foreground alternatives were not executed.
- Old observations were refused, and a fresh snapshot changed its identifier.

Receipts with `effect: unverifiable` were not converted to success. Fresh state
and fixture-side events provide evidence of the actual changes. The script saves
before/after images in ignored `artifacts/`; raw reports/screenshots stay local.

## Scope

These native inputs use Windows UIA/PostMessage routes, not page JavaScript.
Browser extension MAIN-world evaluation is a different Browser Use feature.
General Windows-app JS injection, arbitrary-app background delivery, minimized
windows and input on another virtual desktop are not established by this check.
Native window routes remain available for a browser's currently displayed page;
optional Cua exact-tab tools keep their existing schemas and contracts.
Hardware/focus actions still require one-action consent. See
[WINDOWS_PARITY.md](WINDOWS_PARITY.md) and
[Cursor Studio validation](../../companion/TESTING.md) for earlier scoped evidence.

## Visible replay

The default acceptance run closes its disposable windows. To watch a slower
replay and leave the result open, use:

```powershell
.venv\Scripts\python.exe scripts/live_acceptance_windows.py --driver C:\path\to\cua-driver.exe --output artifacts/visible-replay.json --visible-demo --keep-open --step-delay 5
```

This explicitly displays one disposable target, waits 15 seconds, and confirms
Increment, text insertion, Apply and UIA scroll, pausing between actions. It uses
background input only, never approves a hardware fallback, and does not probe
physical pointer movement. Close the fixture normally when finished. Its log
directory remains under ignored `artifacts/` so the retained window can continue
to write events. The ordinary background acceptance also skips the physical
pointer probe unless `--allow-foreground` was explicitly requested.

The visible replay on 2026-10-08 confirmed all four actions: Count 1, Name/Applied
`Hello from Tobkiri`, and rows 21–28. Fresh screenshots and fixture events agree;
the target process remained open in the user's interactive Windows session.
The user also confirmed seeing it. This adds visible-fixture evidence, not
universal application compatibility. Logs are UTF-8 on Japanese Windows.
