"""Window-relative Cua overlays. Never sends hardware input or takes focus."""
from __future__ import annotations

from dataclasses import dataclass
import threading
import time

from .geometry import Frame
from .transport import ComputerError


# Cua 0.28.2: zero means speed-based motion, NOT instant. On the native 0013
# build, this exact fast profile teleports without a render-arrival wait.
# Unpatched builds retain the positive 1 ms glide and its render-tick wait.
MOTION_PROFILES = {
    "fast": {"glide_duration_ms": 1.0, "dwell_after_click_ms": 0.0,
             "spring": 1.0, "arc_size": 0.0, "arc_flow": 0.0, "turn_radius": 1.0},
    "normal": {"glide_duration_ms": 0.0, "dwell_after_click_ms": 80.0,
               "spring": .72, "arc_size": .25, "arc_flow": 0.0, "turn_radius": 80.0},
}

# Cua 0.28.2 ends an inactive session after five minutes. Window discovery
# does not check the separately named cursors. Poll their actual state while
# they are being followed, through the normal authorized read-only API.
CURSOR_STATE_POLL_SECONDS = 60.0


@dataclass
class Anchor:
    owner: object
    frame: Frame
    x: float
    y: float
    origin: tuple | None = None
    hidden: bool = True
    phase: str = "pending"
    error: str | None = None
    last_state_poll: float = 0.0


class CursorFollower:
    def __init__(self, computer, interval=0.1):
        self.computer = computer
        self.interval = interval
        self._anchors = {}
        self._guard = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._clock = time.monotonic

    def has(self, owner):
        with self._guard:
            return owner.session in self._anchors

    def bind(self, owner, frame, x, y, *, drive=True, rows=None):
        frame.check_pixel(x, y)
        anchor = Anchor(owner, frame, x, y, last_state_poll=self._clock())
        with self._guard:
            previous = self._anchors.get(owner.session)
            if previous is not None:
                anchor.hidden = previous.hidden
            self._anchors[owner.session] = anchor
        try:
            rows = self.computer.windows(pid=owner.surface[0]) if rows is None else rows
            self._update(anchor, rows, force=True, drive=drive)
        except Exception as exc:
            anchor.phase, anchor.error = "error", str(exc)
            raise
        finally:
            with self._guard:
                if self.interval is not None and self._thread is None and not self._stop.is_set():
                    self._thread = threading.Thread(target=self._run, name="tobkiri-window-cursors", daemon=True)
                    self._thread.start()
        return self.status(owner)

    def forget(self, session):
        with self._guard:
            self._anchors.pop(session, None)

    def status(self, owner):
        with owner._lock, self._guard:
            a = self._anchors.get(owner.session)
            if a is None:
                return {"phase": "unbound", "target": owner.target}
            return {"phase": a.phase, "target": owner.target,
                    "local_screen_point": [a.x*a.frame.width/a.frame.pixel_width, a.y*a.frame.height/a.frame.pixel_height],
                    "screen_point": ([a.origin[0]+a.x*a.frame.width/a.frame.pixel_width,
                                      a.origin[1]+a.y*a.frame.height/a.frame.pixel_height] if a.origin else None),
                    "hidden": a.hidden, "error": a.error, "poll_interval_seconds": self.interval,
                    "pixels_verified": False}

    def _hide(self, a, phase):
        if not a.hidden:
            a.owner._call("set_agent_cursor_enabled", enabled=False)
            a.hidden = True
        a.phase = phase

    def _update(self, a, rows, *, force=False, drive=True):
        owner = a.owner
        with owner._lock:
            with self._guard:
                if self._anchors.get(owner.session) is not a:
                    return  # A newer action re-bound this cursor while listing windows.
            if owner._closed or self.computer._closed:
                return
            try:
                matches = [r for r in rows if (r.get("pid"), r.get("window_id")) == owner.surface]
                if len(matches) != 1:
                    self._hide(a, "window_unavailable")
                    self.computer._latest.pop(owner.surface, None)
                    return
                row = matches[0]
                if a.phase in ("geometry_changed", "window_unavailable"):
                    return
                bounds = row.get("bounds", {})
                current = a.frame.at_bounds(bounds)
                if not a.frame.same_size(current):
                    self._hide(a, "geometry_changed")
                    self.computer._latest.pop(owner.surface, None)
                    # Never revive an old anchor merely because a later resize
                    # happens to restore its original dimensions.
                    return
                if not force and self._clock() - a.last_state_poll >= CURSOR_STATE_POLL_SECONDS:
                    # No image refresh, input, or cursor motion. An ended or
                    # revoked session must fail normally; never restart it.
                    owner._call("get_agent_cursor_state")
                    a.last_state_poll = self._clock()
                if row.get("is_on_screen") is False or row.get("on_current_space") is False:
                    self._hide(a, "window_hidden")
                    return
                origin = (current.x, current.y)
                if not force and a.origin == origin and not a.hidden:
                    return
                mode = self.computer.cursor_coordinates
                if mode is None:
                    self._hide(a, "unsupported_driver")
                    raise ComputerError("cursor_contract_unknown", "Calibrate this driver's cursor coordinates before showing an overlay.")
                x, y = current.to_screen(a.x, a.y) if mode == "screen_points" else (a.x, a.y)
                # Exact window target never moves the real OS pointer. Modern
                # target and legacy scope/pid/window_id are mutually exclusive.
                if a.hidden:
                    owner._call("set_agent_cursor_enabled", enabled=True)
                    # Cua's enable command is queued to the render thread. Its
                    # move path skips drawing entirely while disabled. Allow one
                    # render tick on show/re-show, never on ordinary movement.
                    time.sleep(.02)
                if drive:
                    owner._call("move_cursor", target=owner.target, x=x, y=y)
                a.origin, a.hidden, a.phase, a.error = origin, False, "following", None
            except Exception as exc:
                a.error, a.phase = str(exc), "error"
                try:
                    self._hide(a, "error")
                except Exception:
                    pass  # Preserve the first error; reported via cursor status.
                if force:
                    raise

    def tick(self):
        """One deterministic update, also used by the regression tests."""
        with self._guard:
            anchors = list(self._anchors.values())
        if not anchors:
            return
        # One discovery request covers every cursor; no snapshots/cache updates.
        try:
            rows = self.computer.windows()
        except Exception as exc:
            for a in anchors:
                with a.owner._lock:
                    a.error = str(exc)
                    try:
                        self._hide(a, "error")
                    except Exception:
                        a.phase = "error"
            return
        for a in anchors:
            if self._stop.is_set():
                break
            if a.phase == "error":
                continue  # Explicit new observation/move is required to retry.
            self._update(a, rows)

    def _run(self):
        while not self._stop.wait(self.interval):
            self.tick()

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.computer.transport.timeout if hasattr(self.computer.transport, "timeout") else 2)
        with self._guard:
            self._anchors.clear()


class RawCursorOwner:
    """Bind the cursor of a raw Cua session without changing its RPC arguments."""
    def __init__(self, computer, surface, session, lock):
        self.computer, self.surface, self.session, self._lock = computer, surface, session, lock
        self._closed = False

    @property
    def target(self):
        return {"kind": "window", "pid": self.surface[0], "window_id": self.surface[1]}

    def _call(self, name, **args):
        if self.session is not None:
            args["session"] = self.session
        return self.computer.transport.call(name, args)
