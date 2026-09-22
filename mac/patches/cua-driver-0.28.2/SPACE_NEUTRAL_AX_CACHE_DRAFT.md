# Draft 0009: Space-neutral exact AX cache admission

This patch is an unadopted draft. It must not be appended to the eight-patch
candidate without separate review and native evidence.

Patch `0009-macos-exact-ax-cache-space-neutral.patch` removes Space membership
as an admission property for a previously observed exact AX window reference.
It retains every identity check from 0006:

* a current layer-0 WindowServer row with the same PID and `CGWindowID`;
* the same process start timestamp, preventing PID reuse;
* `AXUIElementGetPid` equals the requested PID;
* `_AXUIElementGetWindow` equals the requested `CGWindowID`;
* `AXRole` is exactly `AXWindow`;
* the existing 64-entry LRU bound and no time-only acceptance;
* downstream hidden/minimized checks and competing-window guards.

Current-Space or unknown-Space status does not strengthen those identity
checks. It describes placement, not which native object the retained AX proxy
represents. Requiring `on_current_space == Some(false)` can discard a valid
reference when AppKit temporarily removes the window from `AXWindows` and
`AXChildren` during focus routing while WindowServer and the retained proxy
still report the same identities.

The draft does not guess by title or geometry, switch Spaces, activate an app,
or accept an unreadable cached reference. If any live AX identity read fails,
the current 0006 behavior remains: refuse, release the caller's retain, evict
the cache entry, and require a later fresh exact observation.

## Why the current B fixture is not evidence for adoption

The B fixture remained on Current Space 1, but its application-level
`AXWindows`, `AXChildren`, `AXFocusedWindow`, and `AXMainWindow` reads all timed
out with `kAXErrorCannotComplete` (`-25204`). Process sampling then showed its
main thread blocked inside its `mouseUp` event logger while opening a file. The
input reached the application; an empty event log was not evidence of delivery
failure. Standard Computer also timed out on the blocked app.

Draft 0009 would help only when the retained AX reference itself still passes
all native identity reads. It cannot make an unresponsive target answer AX and
must not be presented as a fix for that fixture failure.

The incident does expose a separate diagnostic defect: `copy_children`,
`copy_ax_windows`, and `copy_element_attr` convert every AX error into an empty
vector or `None`. `get_window_state` then reports `ax_window_unresolved` and
recommends foreground delivery even when the target returned
`kAXErrorCannotComplete`. A follow-up should preserve top-level AX read status
and distinguish a responding empty hierarchy from an unresponsive AX server.
Foreground activation is not a justified remedy for `CannotComplete`.

## Offline verification

```bash
python3 patches/cua-driver-0.28.2/verify_space_neutral_ax_cache_patch.py
```

The verifier applies 0002 AX union, 0006, and draft 0009 to a temporary copy,
runs `rustfmt --check`, checks retained identity invariants and forbidden
fallbacks, and compiles/runs four extracted production admission tests. It
performs no AX calls or GUI input.
