# Patch 0006: exact retained AX window resolution across Spaces

macOS can remove a native AppKit window from both application-level
`AXChildren` and `AXWindows` when the window is on another Space, even while
its screenshot and WindowServer identity remain available. Patch 0006 retains
only AX window references that previously passed an exact
`(pid, CGWindowID)` match.

Both observation and background-input validation use the same resolver. A
retained reference is reused only when every lookup proves:

- WindowServer still reports the requested CGWindowID under the requested pid;
- Space metadata explicitly says the window is off the current Space;
- the pid has the same kernel process-start stamp;
- `AXUIElementGetPid` still reports that pid;
- `_AXUIElementGetWindow` still reports that exact CGWindowID; and
- the live AX role is still `AXWindow`.

`AXFocusedWindow` and `AXMainWindow` are also tried as cold-start native
references when the arrays are empty. A sibling reference is ignored unless it
passes the same exact identity checks. No title, geometry, focus change,
activation, Space switch, or physical input participates in resolution.

Closed, foreign-owner, current-Space, unknown-Space, relaunched-process, and
unreadable AX references are evicted and refused. The cache is process-local,
holds at most 64 retained windows, and refreshes LRU order after successful
live revalidation. Elapsed time alone never disables a still-live exact
off-Space window.

macOS exposes no window-generation token beyond the AX proxy and CGWindowID.
Consequently, a pathological same-pid CGWindowID reuse is indistinguishable if
the old AX proxy continues to report a successful pid, window id, and role
after the replacement. Normal closed-window AX invalidation, WindowServer
absence/owner change, process lifetime checks, and bounded eviction cover the
observable failure modes, but Luna acceptance must still exercise close,
reopen, sibling-window, and off-Space cases.

Apply after the current five-patch series:

```bash
python3 scripts/build_patched_driver.py --resume --compact-native --app-name CuaDriverCandidate6 \
  --patch patches/cua-driver-0.28.2/0001-macos-exact-window-background-drag.patch \
  --patch patches/cua-driver-0.28.2/0002-macos-drag-always-releases-after-mousedown.patch \
  --patch patches/cua-driver-0.28.2/0002-macos-exact-ax-window-union.patch \
  --patch patches/cua-driver-0.28.2/0004-macos-bounded-cursor-arrival.patch \
  --patch patches/cua-driver-0.28.2/0005-macos-drag-single-pid-route.patch \
  --patch patches/cua-driver-0.28.2/0006-macos-off-space-exact-ax-window-cache.patch
```

Run the bounded offline verifier before building:

```bash
python3 patches/cua-driver-0.28.2/verify_off_space_ax_cache_patch.py
```

The parent build preserves the current Apple Development signing identity.
Use a new dedicated socket for this separate app so it cannot attach to the
five-patch daemon. Luna Max owns all live GUI acceptance.
