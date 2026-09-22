# Cua Driver 0.28.2 exact-window background drag patch

This two-patch series enables the native PID-routed drag implementation that is already
present in Cua Driver 0.28.2 and guarantees a release after a posted mouse-down
when intermediate event construction fails. It preserves Tobkiri's input invariants. It is
based on upstream commit `fc188250b4ca8549b8e61f937fdb1fb560770e86` and the
unmodified `drag.rs` SHA-256
`3f65ed593d883560a0079e027aa397858e905089f2003fd3bf16ccc35752d6f7`.

## Interface

The public schema does not change:

```json
{
  "pid": 123,
  "window_id": 456,
  "from_x": 40,
  "from_y": 80,
  "to_x": 220,
  "to_y": 180,
  "delivery_mode": "background"
}
```

`window_id` may be omitted only when the existing `PidOnlyWindowTargetGuard`
can resolve exactly one eligible top-level window and inject its id. Multiple
same-process windows remain an `ambiguous_window_target` refusal.

The background path:

1. acquires Cua's existing per-PID background-mutation lease;
2. gathers fresh `WindowPointer` exact-target facts, including pid/window
   ownership and background eligibility;
3. resolves a fresh capture/frame and refuses non-finite or out-of-window
   endpoints;
4. posts only the existing PID-routed SkyLight plus `CGEventPostToPid` drag
   sequence, stamped with window-local coordinates and f40/f51/f58/f91/f92;
5. keeps the lease through focus restoration and window-change observation.

The native sequence does not warp the hardware pointer and never falls back to
the global HID drag or deliberately activates/fronts the target. The result
remains `verified:false` / `effect:"unverifiable"`; callers must take a fresh
window snapshot to confirm the application-specific effect. The explicit
`delivery_mode:"foreground"` implementation is unchanged.

## Apply and verify

From an exact Cua checkout, apply both patches in order:

```bash
patch -p1 < /path/to/0001-macos-exact-window-background-drag.patch
patch -p1 < /path/to/0002-macos-drag-always-releases-after-mousedown.patch
```

The offline verifier checks both source hashes, clean ordered patch application, removal
of the hard refusal, and presence/order of the target gate, bounds validation,
PID-routed dispatch, exclusive-edge Rust unit coverage, and release-after-down
lifecycle:

```bash
python3 patches/cua-driver-0.28.2/verify_patch.py
```

When disk space permits, use an isolated target directory and run only the
platform crate check/test before attempting an application bundle build:

```bash
cd artifacts/cua-source/libs/cua-driver/rust
CARGO_TARGET_DIR=/path/with-space/cua-target cargo check -p platform-macos
CARGO_TARGET_DIR=/path/with-space/cua-target cargo test -p platform-macos \
  background_drag_accepts_only_finite_in_frame_endpoints
```

The current host has about 1.6 GiB free, so no Rust build was started while
preparing this patch.

## Deployment constraints

The installed `/Applications/CuaDriver.app` is Developer ID signed by team
`YCK386LBJ7`. A locally rebuilt or ad-hoc-signed binary has a different code
identity and must not be assumed to inherit the installed app's Accessibility,
Screen Recording, or Input Monitoring grants. Do not replace the installed app
or restart the shared daemon. Build a separate app/runtime, sign it with the
intended identity, explicitly grant its required macOS permissions, and point
Tobkiri's dedicated socket configuration at that runtime only after review.

Live acceptance must be performed by the designated Luna Max GUI operator on
dedicated fixture windows. It should prove: the target changes, a same-pid
sibling does not change, the frontmost app/window stays the same, the hardware
pointer stays at its sampled position, and the returned path is `cgevent` with
`verified:false`.

## Remaining native transport limitation

`post_mouse_event_with_mode(..., MousePostMode::Both)` currently invokes both
`SLEventPostToPid` and public `CGEventPostToPid` for every PID-routed drag
event. If a target consumes both routes, it may see duplicate down/drag/up
events. The private call's boolean only says that the symbol was available and
invoked; neither route provides a target-consumption acknowledgement. Changing
the sequence to private-with-public-fallback would avoid duplicates but can
silently regress AppKit/WebKit targets when the private post returns normally
without being consumed. Patch 0002 therefore fixes the provable stuck-button
failure without changing this compatibility behavior. A transport change needs
Luna-run live coverage across Chromium, AppKit, and WebKit fixtures before it
is safe to ship.

Patch 0002 preconstructs `mouseUp` before posting `mouseDown`, captures any
intermediate construction error, posts the prepared release, and only then
returns the original error. It adds no HID post, cursor warp, or activation.
An unrecoverable process abort or panic remains outside this in-process cleanup
guarantee.
