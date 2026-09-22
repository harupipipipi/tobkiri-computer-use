# Patches 0007–0008: one route per raw pointer event

These patches apply after 0006. They do not add HID input, pointer warps,
foreground fallback, delayed retry, or target-check bypasses.

`0007-macos-pointer-single-pid-route.patch` removes the remaining raw-pointer
`Both` mode. Background right-click, middle-click, targeted wheel, pid-only
legacy click, and background interactive pointer/scroll now attempt one
SkyLight PID post. The public PID post is used once only when the SkyLight
symbol is unavailable. A successful private function invocation is not treated
as application acknowledgement and is never followed by a speculative public
post.

Foreground exact-window right/middle/wheel calls explicitly select the public
PID route, matching the existing exact-window left-click policy. Desktop and
persistent-foreground interactive modes keep their existing explicit HID path.
Exact-window middle click now carries the validated `CGWindowID` into the
f51/f91/f92 stamps instead of degrading to a pid-only post.

The legacy no-window APIs are also private-first single-route. They still lack
an exact window address and are retained only for existing callers which have
no `CGWindowID`. This changes their duplicate-delivery behavior and may expose
an AppKit/WKWebView receiver which accepts only the public route. There is no
receipt acknowledgement with which to implement a safe second-route retry.

`0008-macos-standalone-right-click-focus-guard.patch` is deliberately separate.
It wraps the standalone right-click pixel branch with the same background
focus-suppression and window-change observation used by
`click(button="right")`. Explicit foreground mode continues to own its brief
front-and-restore sequence.

## Offline verification

```bash
python3 patches/cua-driver-0.28.2/verify_pointer_single_route_patch.py
```

The verifier copies pinned upstream source into a temporary directory, applies
the complete 0001–0008 series in order, runs `rustfmt --check`, checks all
reviewed call paths, and compiles/runs the extracted production route helper's
Rust unit tests. It performs no GUI or native input.

## Separate candidate build

Use the package builder so the pinned series is applied to a generated source
copy. For a build which already contains patches through 0006, append 0007 and
0008 with `--resume` and repeat the complete recorded prefix:

```bash
python3 scripts/build_patched_driver.py --resume \
  --app-name CuaDriverCandidate8 \
  --patch patches/cua-driver-0.28.2/0001-macos-exact-window-background-drag.patch \
  --patch patches/cua-driver-0.28.2/0002-macos-drag-always-releases-after-mousedown.patch \
  --patch patches/cua-driver-0.28.2/0002-macos-exact-ax-window-union.patch \
  --patch patches/cua-driver-0.28.2/0004-macos-bounded-cursor-arrival.patch \
  --patch patches/cua-driver-0.28.2/0005-macos-drag-single-pid-route.patch \
  --patch patches/cua-driver-0.28.2/0006-macos-off-space-exact-ax-window-cache.patch \
  --patch patches/cua-driver-0.28.2/0007-macos-pointer-single-pid-route.patch \
  --patch patches/cua-driver-0.28.2/0008-macos-standalone-right-click-focus-guard.patch
```

`--resume` requires the same generated output and app name recorded by the
prior build. Use the actual recorded app name rather than the example if it
differs.

## Native acceptance still required

The void post APIs cannot prove application consumption. Luna should compare
one-event counters and visible effect for AppKit, Chromium, and WKWebView:

* one right-click produces one context-menu callback;
* one wheel notch produces one measured scroll delta;
* middle-click produces one down/up gesture in the exact window;
* sibling windows remain unchanged;
* background mode preserves the prior foreground PID and hardware pointer;
* foreground mode uses its documented brief front-and-restore behavior.

The AppKit fixture's successful single-route drag shows that SkyLight can reach
that fixture, but does not establish compatibility for every AppKit or WebKit
control.
