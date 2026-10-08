# Fast macOS cursor teleport

Patch `0013-macos-fast-cursor-teleport.patch` applies after the Candidate12
series on Cua Driver 0.28.2, pinned commit
`fc188250b4ca8549b8e61f937fdb1fb560770e86`.

Tobkiri's existing `fast` motion profile now selects teleport on this patched
native build: `glide_duration_ms=1`, `dwell_after_click_ms=0`, `spring=1`,
`arc_size=0`, `arc_flow=0`, and `turn_radius=1`. Matching all six settings
keeps normal animation and other caller-selected motion profiles unchanged.
Zero glide duration continues to mean Cua's speed-based animation.

The native `animate_cursor_to` entry point enqueues the existing `SnapTo`
command and returns before any path planning, render tick, arrival channel,
or spring settling. It uses the same 16-point cursor-tip offset as native
pointer tracking. Clicks and other actuators retain their original target,
geometry, background eligibility, focus, consent, and result verification.
No tool schema or successful tool output changes.

Only accepted motion commands enter a session-local requested-policy cache.
The next action sees that policy even before the render thread consumes the
setting. Partial motion updates retain prior accepted settings. Session
removal and revival clear the cache. A full, unavailable, or disconnected
teleport queue remains a native refusal before the request's input. A
superseded animation waiter is cancelled rather than acknowledged as arrived.
The renderer retains its ended-session tombstone guard.

Queue acceptance means the position update was queued. It does not prove
that the next screenshot contains the new cursor pixels. Immediate render
state reads can still report the previous position; wait for observed state
when inspecting the artwork, without delaying input for that purpose.

The Python helper's `fast` setting remains compatible with unpatched 0.28.2:
there it still selects a 1 ms animation and can wait for rendering. True
teleport therefore requires this specific native patch, not merely a version
string of `0.28.2`. Historical latency measurements are not measurements of
this new build. Screenshots, AX queries, IPC, native press/release timing,
and application processing still take time.

Offline verification (no daemon or desktop input):

```sh
.venv/bin/python patches/cua-driver-0.28.2/verify_fast_cursor_teleport_patch.py
```

Append 0013 to the explicit Candidate12 patch list in
[`NATIVE_DRIVER_PATCHES.md`](../../docs/NATIVE_DRIVER_PATCHES.md), retaining all
earlier patch hashes. Build a separate candidate:

The command below resumes the existing generated Candidate12 source. For a
fresh build with no generated source, omit `--resume`.

```sh
.venv/bin/python scripts/build_patched_driver.py --resume --compact-native \
  --app-name CuaDriverCandidate13Teleport \
  --patch patches/cua-driver-0.28.2/0001-macos-exact-window-background-drag.patch \
  --patch patches/cua-driver-0.28.2/0002-macos-drag-always-releases-after-mousedown.patch \
  --patch patches/cua-driver-0.28.2/0002-macos-exact-ax-window-union.patch \
  --patch patches/cua-driver-0.28.2/0004-macos-bounded-cursor-arrival.patch \
  --patch patches/cua-driver-0.28.2/0005-macos-drag-single-pid-route.patch \
  --patch patches/cua-driver-0.28.2/0006-macos-off-space-exact-ax-window-cache.patch \
  --patch patches/cua-driver-0.28.2/0007-macos-pointer-single-pid-route.patch \
  --patch patches/cua-driver-0.28.2/0008-macos-standalone-right-click-focus-guard.patch \
  --patch patches/cua-driver-0.28.2/0010-macos-ax-top-level-read-diagnostics.patch \
  --patch patches/cua-driver-0.28.2/0011-macos-pixel-hit-test-axpress-eligibility.patch \
  --patch patches/cua-driver-0.28.2/0012-macos-window-frame-required-mutations.patch \
  --patch patches/cua-driver-0.28.2/0013-macos-fast-cursor-teleport.patch
```

Run the pure overlay tests with `cargo +stable test --locked -p platform-macos
--lib cursor::overlay::tests::`. This filter sends no GUI input. Live timing
and application effects require the opt-in dedicated TobkiriFixture acceptance
script; ordinary tests do not measure those effects.

## Verification on 2026-10-04

The signed Candidate13 executable had SHA-256
`43a535924a8bc820bf1468b9f73d148db0f1e970c4a40e4b395e6f6f5876ba84`.
The offline patch verifier, 26 pure native overlay tests (including seven
teleport regressions), 266 Python tests, and all eight dedicated fixture
acceptance checks passed. The fixture checked real counter changes, stale
coordinate refusals, zoom input, translated-window input, and two independent
window cursors. Reported cursor positions do not prove painted overlay pixels.

The opt-in latency run compared two profiles on this same native build,
with six samples per operation and profile:

| Host RPC operation (median) | Normal animation | Fast teleport |
| --- | ---: | ---: |
| Virtual cursor move | 1.165 s | 0.049 s |
| Pixel click plus fresh observation | 1.657 s | 0.551 s |

This is a comparison with the normal animated profile, not a before/after
comparison with the old 1 ms fast profile. It measures this fixture's host
calls, not OS event onset or a universal application latency. Twelve timeline
clicks produced twelve counter increments in 3.683 s including the final
observation. Their requested 25 ms spacing was stretched by `on_late="stretch"`;
the run did not achieve 40 clicks per second. Native target checks and app
readback remain part of the time after animation waiting is removed.

To reproduce on an already running candidate socket without changing the
saved runtime configuration, use paths relative to the macOS package:

```sh
.venv/bin/python scripts/live_acceptance.py \
  --driver artifacts/patched-driver/CuaDriverCandidate13Teleport.app/Contents/MacOS/cua-driver-local \
  --socket artifacts/teleport-test.sock \
  --output-dir artifacts/teleport-live --measure-latency
```

For a visible demonstration using the configured runtime and already running
TobkiriFixture windows, omit the profile comparison and run:

```sh
.venv/bin/python scripts/live_acceptance.py \
  --fast-demo --output-dir artifacts/teleport-demo
```

This performs 36 fast moves between observed AX control centers and requests
twelve counter clicks in each window with no added spacing. It checks both
counter increases and saves the final observations. Same-process native input
can still serialize; the demo reports actual elapsed time. Add
`--wait-demo-start` to inspect the saved initial images before pressing Enter;
the script takes fresh observations after that pause. This mode never selects
the normal animated profile.

Raw reports, screenshots, native build records and adoption evidence stay in
ignored `artifacts/`. Local adoption verification reloaded a
standard/existing-profile MCP worker and confirmed its native child used the
same binary hash and managed socket.
Other already connected MCP workers adopt the saved selection when reloaded
or reconnected; changing the configuration does not restart their operations.
