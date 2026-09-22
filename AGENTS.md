# Tobkiri Computer Use

Work only in this checkout. The neighboring `devin` directory belongs to a
different agent; never edit it or operate its music/browser demo.

This package wraps Cua Driver through a persistent MCP connection. Keep original
Cua schemas and outputs intact; helper tools use `tobkiri_` names. Never silently
retry input or convert unknown effects to success. Permission setup is a trusted
host operation: change it when the user requests it, never as an input fallback.

Coordinate input uses snapshot-bound screenshot pixels. Native screen points,
image pixels, and zoom pixels are distinct. Keep transforms and the 0.28.2 macOS
cursor workaround explicit, versioned, and tested. Do not assume a driver update
retains the old cursor contract.
Pure window translation must preserve the logical observation and image/zoom
coordinates. Refresh native frame/token caches internally, compare local layout,
and keep overlays bound to the exact window. Resizes invalidate old coordinates.
Never combine modern Cua target with legacy scope/pid/window_id fields.
Cua native window operations remain available for browsers. Tab/CDP tools are
an optional exact-tab route; their refusal must never disable native AX/pixels.
A native action only reaches the currently displayed page. Reobserve it and do
not overwrite the user's address bar or change tabs as a recovery tactic.
Ordinary virtual cursor/background actions do not require another human prompt.
The user's chosen startup policy is standard + existing-profile grant for the
dedicated Tobkiri runtime. Keep native checks and per-action hardware/focus consent.
Desktop observations and window-targeted overlays are not hardware takeover.
Native move_cursor with a desktop target/scope is physical pointer input and
must use the same consent gate as other hardware input.
Login, transmission, deletion, purchases and other consequential UI actions follow
the bundled Computer confirmation rules and the user's current instructions.
Page autoplay is not a stream of agent input events or cursor positions.

The macOS package, scripts, tests, patches, and skill live under `mac/`.
Run `cd mac` and then `.venv/bin/python -m pytest`. For actual GUI checks, use only the dedicated
TobkiriFixture windows and the opt-in `scripts/live_acceptance.py`. Ordinary tests
must not interact with the user's desktop. Do not edit PR #1322's checkouts.
Keep generated artifacts, screenshots, raw logs, local benchmark configurations,
and local compatibility symlinks out of Git. The published benchmark templates
are path-normalized; preserve the original local prompts and historical hashes.
