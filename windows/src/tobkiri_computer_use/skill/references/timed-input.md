# Timed background input

Use this for a sequence of clicks on a static, observed UI, such as piano keys.
Read the page first and derive coordinates from its current screenshot/AX frames.
Do not reuse a memorized layout or mix screenshot pixels with DOM coordinates.

```python
from tobkiri_computer_use import Computer, ClickStep

with Computer() as computer:  # helper cursors default to fast
    window = computer.window(pid=PID, window_id=WINDOW_ID)
    right = computer.mouse("right", pid=PID, window_id=WINDOW_ID)
    state = window.observe()
    p = state.point(X1, Y1)  # measured in this screenshot
    q = state.point(X2, Y2)
    result = window.timeline([
        ClickStep(0.00, p),
        ClickStep(0.25, q, right),
        ClickStep(0.50, p),
    ])
    print(result.status, result.events)
    print(result.observation.tree)
```

All steps use points from the main window handle's same fresh observation.
Additional named cursors must belong to the same `Computer` and exact window.
They need no separate observation. Input within a window is serialized; the
separate cursors visualize their own events, not independent physical mice.

`at` is seconds from the sequence epoch, ordered and finite, at most 120 seconds.
A call accepts 1..2000 steps. Python can provide an absolute `start_at` from
`time.monotonic()` to synchronize jobs on different windows with
`computer.parallel(...)`. Choose a future start to allow preparation. Supply a
`threading.Event` as `stop_event` for cancellation.

The default `max_lateness=.25` stops a sequence that cannot keep the requested
tempo; no catch-up burst is emitted. Inspect partial results before changing the
tempo. Recorded times are dispatch start/completion, not measured sound onset.
If completing the sequence matters more than keeping the requested tempo, select
`on_late="stretch"`: it shifts future deadlines and reports
`schedule_shift_seconds`. It does not claim to meet the original tempo or retry
an already attempted click. Refusal, geometry errors and transport errors still stop.
Cua can serialize events for the same app/PID even across different windows.
This does not guarantee sample-accurate music, simultaneous chords, or held notes;
each step is a complete native click, with native press/release timing.

The sequence avoids full AX/screenshot reads per beat, but checks current window
identity, title, visibility, size and sibling overlap before every click. Window
translation refreshes Cua's pixel transform. Resize, changed title, overlap,
refusal or transport error/timeout stops further input; missed deadlines use the
selected stop/stretch policy. The final
observation records actual state; delivered/unverifiable is not success proof.
Generic Cua clicks commonly return unverifiable; those results are retained and
the sequence can continue, with outcome verification at the end.

Split and observe again before scrolling, navigating or changing layout. There
is no per-step image comparison, so title-preserving layout changes are outside
this static-sequence contract. For evolving UIs, use normal `window.click()`.
Login, purchases, transmission and other consequential steps belong outside a
pre-scheduled sequence unless the user's authorization specifically covers them.
Timeline has no foreground/desktop mode and never borrows hardware input.

MCP: first `tobkiri_observe`, then `tobkiri_timeline` with the returned
`observation_id` and `steps=[{"at":0,"point":[x,y],"cursor":"left"}, ...]`.
The top-level cursor identifies the observation owner. Per-step `cursor` names
select additional virtual cursors in the same exact window.

Native Cua callers can configure their own named session with
`set_agent_cursor_motion(session=..., glide_duration_ms=1, dwell_after_click_ms=0,
spring=1, arc_size=0, arc_flow=0, turn_radius=1)`. Zero glide duration selects
speed-based motion; it is not instant. Configuration is queued to the render
thread, so an immediate state read can still show old values. Helpers handle
the session setting and keep a fast pre-move for Cua's pixel-to-AX shortcut,
which otherwise can return without updating the visual cursor.
