# Bounded macOS cursor arrival

Patch 0004 targets cua-driver 0.28.2 source commit
fc188250b4ca8549b8e61f937fdb1fb560770e86.

The macOS overlay previously dropped a full or disconnected command queue and
then awaited its arrival channel without a deadline. Click, drag, and related
tools wait for that visual arrival before their native actuator, so the dropped
MoveTo could leave an otherwise valid request pending forever.

The patch makes the MoveTo enqueue observable and limits its render-arrival
wait to 15 seconds. Queue unavailable, full, disconnected, superseded, and
timed-out moves return a structured refusal before any input or semantic
mutator in that request. A timed-out waiter is removed only when its ticket is
still current, so it cannot erase a later move for the same session.

Existing best-effort overlay commands remain non-blocking. The bounded path is
used only by the animation whose success gates a later action.

Repeated-point calls remain ordinary successful animations. The path planner
already routes a sub-half-point move through its linear fallback with a minimum
one-point path. With a 1 ms configured glide, a normal 2 ms render tick signals
arrival. The patch has a pure regression test for this case because helper
pre-moves often make the following click or drag target identical.

Apply after the selected baseline 0.28.2 patches. Verify without a native
daemon, GUI, Cargo build, or input dispatch:

    python3 patches/cua-driver-0.28.2/verify_cursor_arrival_patch.py

The verifier checks patch applicability against the pinned pristine source,
required bounded-path and refusal markers, all direct animation callers, and
the absence of focus, pointer-warp, or event-posting additions.
