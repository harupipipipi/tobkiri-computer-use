# Patch 0005: one PID transport per background drag event

Apply this after the existing background-drag and release-cleanup patches:

```bash
patch -p1 < patches/cua-driver-0.28.2/0001-macos-exact-window-background-drag.patch
patch -p1 < patches/cua-driver-0.28.2/0002-macos-drag-always-releases-after-mousedown.patch
patch -p1 < patches/cua-driver-0.28.2/0005-macos-drag-single-pid-route.patch
```

The original drag helper sends every down, dragged, and up event through both
`SLEventPostToPid` and `CGEventPostToPid`. The Luna Max native preflight
issued one background drag against the AppKit drawing fixture and observed one
visible line but two recorded strokes. Patch 0005 confines the correction to
drag: each event uses SkyLight when its symbol is available, otherwise exactly
one public PID post. It retains the existing PID and window stamps, exact-target
gate, window bounds check, mouse-up cleanup, and physical-pointer preservation.
It adds no HID post, cursor warp, activation, or foreground fallback.

`SLEventPostToPid` is a void API. A resolved invocation is not an
application-consumption acknowledgement, so the public post cannot safely be
retried after it. This policy follows the existing single-route Chromium click
recipe in `click_at_xy_chromium`. The source documents SkyLight as the route
needed by Chromium and Catalyst; the live AppKit fixture's two-stroke result is
evidence that it also consumed that route on the tested host. WebKit and AppKit
controls that accept only the public route on a system where SkyLight resolves
remain a compatibility risk and require Luna-run fixture coverage. Raw pixel
click, right-click, and wheel code still contains dual-route delivery; the
successful button preflight used the AX action path and does not establish that
raw pixel click is free of duplication.

Run the focused offline verifier without Cargo or GUI input:

```bash
python3 patches/cua-driver-0.28.2/verify_drag_single_route_patch.py
```

Resume the generated patched-driver build with its complete recorded four-patch
prefix and append patch 0005:

```bash
python3 scripts/build_patched_driver.py --resume --compact-native \
  --patch patches/cua-driver-0.28.2/0001-macos-exact-window-background-drag.patch \
  --patch patches/cua-driver-0.28.2/0002-macos-drag-always-releases-after-mousedown.patch \
  --patch patches/cua-driver-0.28.2/0002-macos-exact-ax-window-union.patch \
  --patch patches/cua-driver-0.28.2/0004-macos-bounded-cursor-arrival.patch \
  --patch patches/cua-driver-0.28.2/0005-macos-drag-single-pid-route.patch
```

This builder applies and records the patch series in
`artifacts/patched-driver/source`, compiles that generated source, and
packages the separate local candidate app. Do not run Cargo from pristine
`artifacts/cua-source`. Keep the candidate's dedicated identity and socket;
do not replace or restart the installed shared CuaDriver daemon. Luna Max must
repeat the drag preflight and confirm one recorded stroke, real canvas change,
unchanged foreground and hardware pointer, and no effect in a sibling window.
