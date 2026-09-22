# Raw pointer PID-route audit (Cua 0.28.2 + patches 0001–0006)

This is a source-only audit. It does not claim application receipt from a void
post API, and it does not replace the AppKit/Chromium/WebKit live matrix.

## Finding

The drag-only 0005 patch fixes only `drag_at_xy_observed`. Other background
pointer paths still call both `SLEventPostToPid` and `CGEventPostToPid` for the
same native event. A receiver which accepts both sees two events. The observed
AppKit drag duplication proves that this is not merely theoretical for the
current machine and signing context.

The remaining paths are:

* `right_click_at_xy_inner`: its leading `mouseMoved`, `rightMouseDown`, and
  `rightMouseUp` all use `MousePostMode::Both`
  (`input/mouse.rs` upstream lines 1024–1062; patched-source lines 1061–1099).
  One logical right-click can therefore enqueue two primers, two downs, and two
  ups.
* `scroll_wheel_at_xy`: the primer uses `Both`, and every wheel tick explicitly
  calls SkyLight followed by the public PID post (upstream lines 1244–1298;
  patched-source lines 1315–1369). A receiver accepting both can scroll twice
  the requested amount.
* middle click: both down and up use the generic `post_mouse_event` (upstream
  lines 936–971). Its “with window local” API does not accept or stamp a
  `CGWindowID`, so it also lacks the exact f51/f91/f92 window route used by
  right and left clicks.
* pid-only left click (`click_at_xy`, used when no window id exists) selects
  `Both` at upstream line 54. The exact-window left-click path is already
  single-route: background uses `click_at_xy_chromium`, whose local dispatcher
  invokes public delivery only if the SkyLight symbol is unavailable; foreground
  uses `PublicOnly` (upstream lines 259–289 and 438 onward).
* background interactive input calls the same generic dual dispatcher for both
  pointer events and scroll events (`input/interactive.rs` lines 567–579 and
  611–630). Foreground interactive input instead posts once to the HID tap.

`skylight::post_to_pid` returns `true` when the private symbol resolved and the
void function was invoked, not when the application consumed the event
(`input/skylight.rs` lines 308–351). Consequently, posting public after a
SkyLight invocation is a second delivery, not a receipt-based fallback. There
is no safe retry signal here.

## Focus behavior is separate

For a background, exact-window **left** pixel click, `click.rs` deliberately
selects `AllowTargetWithoutRaise` (lines 87–99) and calls
`prepare_background_pixel_click` (lines 984–1013). That helper invokes
`activate_without_raise`, which posts a defocus record to the old front process
and a focus record to the target process/window (`input/skylight.rs` lines
491–548). The tool then observes the frontmost process and restores the prior
application when appropriate (`click.rs` lines 1114–1135). This activation
sequence, rather than dual event posting, is the direct source-level reason a
raw left pixel click can transiently change application focus.

`delivery_mode:foreground` is intentionally stronger: `with_foreground_assist`
sets the target process frontmost, makes the exact window key, waits for AX
focus, runs the input body, and restores the prior process
(`input/skylight.rs` lines 663–735).

Background right and middle clicks through the generic `click` tool use
`SuppressTarget` and its focus guard. The separate `right_click` tool does not
wrap its pixel branch in `WindowChangeDetector`/`with_focus_suppressed`; it only
uses foreground assist when foreground mode is requested
(`tools/right_click.rs` lines 204–287). Thus a target which self-activates on a
background context click may remain active. Removing duplicate posts can reduce
duplicated side effects, but does not by itself supply the missing focus guard.

Targeted wheel delivery is wrapped in focus suppression, and foreground wheel
delivery intentionally uses foreground assist (`tools/scroll.rs` lines
515–559).

## Recommended patch shape

A follow-up patch should make every route explicit and remove
`MousePostMode::Both` rather than silently changing its meaning:

1. Reuse 0005's `post_single_pid_route`. Background exact-window, pid-only, and
   interactive pointer events choose `SkyLightWithPublicFallback`. The fallback
   remains symbol-availability-only.
2. Thread `WindowClickDelivery` into right click, middle click, and targeted
   wheel helpers. Foreground-assist callers choose `PublicOnly`, matching the
   existing exact-window left-click behavior. Background callers choose
   `SkyLightWithPublicFallback`.
3. Route the wheel event through `post_mouse_event_with_mode` (or a small shared
   stamped-event dispatcher) once per tick instead of retaining the separate
   two-call block.
4. Add `wid` to the middle-click exact-window helper and stamp it. Do not call a
   pid-only primitive after an exact target was validated.
5. Keep desktop foreground/HID helpers unchanged. They are a separate, explicit
   physical-input mode.
6. Separately wrap the standalone `right_click` pixel branch with the same
   focus-suppression/observation policy used by `click(button=right)`. This is a
   focus-integrity correction, not part of transport de-duplication.

Changing the generic dispatcher globally without plumbing delivery posture is
too broad: foreground-assist paths currently call some of the same helpers, and
the code has intentionally selected `PublicOnly` for foreground exact-window
left clicks. Explicit mode propagation keeps that distinction reviewable.

## Compatibility limits

The upstream comments say SkyLight is needed for Chromium/Catalyst while the
public PID route reaches AppKit/WKWebView targets on which SkyLight may drop
events (`input/mouse.rs` lines 1–11 and 1067–1074). The current AppKit fixture
accepted SkyLight for drag, but that does not prove every AppKit or WebKit
control accepts it. Because neither void post API acknowledges application
receipt, the driver cannot safely perform a delayed second-route fallback.
Private-first single delivery is the consistent exactly-once choice already
used by patched drag and background exact-window left click, with a known risk
that public-only receivers may stop responding. That risk requires live matrix
coverage rather than a speculative dual post.

## Meaningful verification

Production unit tests should exercise the actual route-selection helper and
mode mapping:

* private symbol available: N native events cause exactly N private calls and
  zero public calls;
* private symbol unavailable: N native events cause N attempted private calls
  and exactly N public calls;
* background right-click sequence: primer + down + up produces three total
  delivery calls, never six;
* `ticks = 3` wheel sequence: primer + three wheel events produces four total
  delivery calls, never eight;
* foreground mode selects public-only and does not invoke the private closure;
* exact-window middle click preserves the supplied `CGWindowID` in its stamp
  arguments;
* a source verifier rejects any remaining `MousePostMode::Both` and direct
  adjacent SkyLight/public posts in pointer code.

Live Luna validation should then count application effects, not only API
success: one AppKit context-menu callback, one Chromium `contextmenu` callback,
one WebKit/WKWebView context menu, measured one-notch scroll deltas in all three,
unchanged sibling window, restored foreground, and unchanged physical pointer.
The standalone `right_click` focus test must be included because its present
focus policy differs from `click(button=right)`.
