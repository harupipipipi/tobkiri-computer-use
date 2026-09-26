"""Monotonic scheduling for bounded, static, observed native window targets.

This batches observations, not safety policy: each event keeps exact-window
geometry/visibility/overlap checks and Cua's background delivery/focus guard.
"""
from dataclasses import dataclass
import math
import threading
import time

from .geometry import Frame, segment_intersects_rect
from .models import Point
from .transport import ComputerError, structured


@dataclass(frozen=True)
class ClickStep:
    at: float
    point: Point
    cursor: object = None


@dataclass
class TimelineResult:
    status: str
    events: list
    observation: object
    elapsed: float
    error: dict | None = None

    def to_dict(self):
        return {"status": self.status, "events": self.events,
                "elapsed_seconds": self.elapsed, "error": self.error,
                "timing": "dispatch start/completion, not measured OS or audio onset",
                "observation": self.observation.to_dict(diff=True) if self.observation else None}


def _live_frame(window, snapshot):
    rows = window.computer.windows(pid=window.surface[0])
    target = next((r for r in rows if r.get("window_id") == window.surface[1]), None)
    if target is None or target.get("is_on_screen") is False or target.get("on_current_space") is False:
        raise ComputerError("stale_geometry", "Timeline target is no longer visible; remaining input was stopped.")
    frame = snapshot.frame.at_bounds(target.get("bounds", {}))
    if not snapshot.frame.same_size(frame):
        raise ComputerError("stale_geometry", "Timeline target resized; observe its new layout before continuing.")
    title = snapshot.raw.get("window_title")
    if title and target.get("title") and title != target["title"]:
        raise ComputerError("stale_observation", "Timeline window title/page changed; remaining input was stopped.")
    return frame, rows


def run_timeline(window, steps, *, start_at=None, max_lateness=.25, on_late="stop", stop_event=None):
    if on_late not in ("stop", "stretch"):
        raise ValueError("on_late must be stop or stretch")
    if not isinstance(max_lateness, (int, float)) or not math.isfinite(max_lateness) or not 0 <= max_lateness <= 5:
        raise ValueError("max_lateness must be finite and between 0 and 5 seconds")
    if start_at is not None and (not isinstance(start_at, (int, float)) or not math.isfinite(start_at)):
        raise ValueError("start_at must be a finite time.monotonic() timestamp")
    steps = tuple(steps)
    if not 1 <= len(steps) <= 2000:
        raise ValueError("Use 1..2000 ClickSteps per timeline")
    stop = stop_event if stop_event is not None else threading.Event()
    records, error, final = [], None, None
    with window.computer._inputs.hold(), window._lock:
        if window._closed or window.computer._closed:
            raise ComputerError("closed", "Window session is closed")
        snapshot = None
        last_time = -1
        for step in steps:
            if (not isinstance(step, ClickStep) or isinstance(step.at, bool)
                    or not isinstance(step.at, (int, float)) or not math.isfinite(step.at)
                    or not 0 <= step.at <= 120 or step.at < last_time or not isinstance(step.point, Point)):
                raise ValueError("ClickSteps require ordered finite seconds (0..120) and snapshot-bound Points")
            snapshot = window._fresh(step.point)
            if snapshot.frame is None:
                raise ComputerError("no_pixel_frame", "Observe a screenshot before scheduling clicks")
            snapshot.frame.check_pixel(step.point.x, step.point.y)
            cursor = step.cursor or window
            if (getattr(cursor, "computer", None) is not window.computer
                    or cursor.surface != window.surface or cursor._closed):
                raise ComputerError("target_mismatch", "Every cursor must belong to this Computer and exact window")
            last_time = step.at
        frame, rows = _live_frame(window, snapshot)
        origin = (snapshot.frame.x, snapshot.frame.y)
        # Start after validation by default. Supplying a shared future start_at
        # allows independent windows to use the same Python clock.
        epoch = time.monotonic() if start_at is None else start_at
        status, schedule_shift = "completed", 0.
        window.computer._latest.pop(window.surface, None)
        try:
            for index, step in enumerate(steps):
                remaining = epoch + step.at + schedule_shift - time.monotonic()
                if stop.wait(max(0, remaining)):
                    status = "cancelled"
                    break
                frame, rows = _live_frame(window, snapshot)
                if (frame.x, frame.y) != origin:
                    # Refresh Cua's screenshot transform after translation, but
                    # do not walk the AX tree at every beat. Local pixels stay put.
                    raw = structured(window._call("get_window_state", pid=window.surface[0], window_id=window.surface[1],
                        include_accessibility_tree=False, include_screenshot=True,
                        max_dimension=window._last_options["max_dimension"]))
                    b = raw.get("window_bounds", {})
                    refreshed = Frame(*(b[k] for k in ("x", "y", "width", "height")),
                                      snapshot.frame.pixel_width, snapshot.frame.pixel_height)
                    if ((raw.get("pid"), raw.get("window_id")) != window.surface
                            or not raw.get("screenshot_frame_valid", True) or not snapshot.frame.same_size(refreshed)
                            or abs(refreshed.x-frame.x) > .5 or abs(refreshed.y-frame.y) > .5):
                        raise ComputerError("stale_geometry", "Window moved during capture; remaining input was stopped")
                    origin = (frame.x, frame.y)
                position = frame.to_screen(step.point.x, step.point.y)
                for sibling in rows:
                    if sibling.get("window_id") == window.surface[1] or sibling.get("is_on_screen") is False or sibling.get("on_current_space") is False:
                        continue
                    bounds = sibling.get("bounds", {})
                    if all(k in bounds for k in ("x", "y", "width", "height")) and segment_intersects_rect(position, position, bounds):
                        raise ComputerError("overlapping_window", "A sibling window intersects the click; remaining input was stopped")
                cursor = step.cursor or window
                # Cua's background pixel→AX shortcut skips its own cursor move.
                # Keep one fast visual pre-move; it never moves the OS pointer.
                cursor._bind_cursor(snapshot, step.point, rows=rows)
                now = time.monotonic()
                scheduled_at = step.at + schedule_shift
                lateness = max(0., now - (epoch + scheduled_at))
                if stop.is_set():
                    status = "cancelled"
                    break
                if lateness > max_lateness:
                    if on_late == "stop":
                        raise ComputerError("timeline_late", "Input could not keep this tempo; stopped instead of emitting a catch-up burst",
                                            details={"index": index, "lateness_seconds": lateness})
                    # Explicit best-effort playback shifts future deadlines;
                    # report the drift instead of pretending the tempo was met.
                    schedule_shift += lateness
                record = {"index": index, "at": step.at, "cursor": cursor.session,
                          "started": now-epoch, "lateness_seconds": lateness,
                          "scheduled_at": scheduled_at, "schedule_shift_seconds": schedule_shift,
                          "point": [step.point.x, step.point.y]}
                records.append(record)
                try:
                    driver_x, driver_y = window._driver_coordinates(snapshot, step.point.x, step.point.y)
                    result = structured(cursor._call("click", target=window.target, x=driver_x, y=driver_y,
                                                      delivery_mode="background"))
                except ComputerError as exc:
                    record["error"] = exc.as_dict()
                    record["outcome"] = "unknown; input may have landed"
                    raise
                finally:
                    record["completed"] = time.monotonic()-epoch
                record["delivery"] = result
                if result.get("effect") == "refused" or result.get("status") == "refused" or result.get("refusal"):
                    status = "refused"
                    break
                cursor._sequence += 1
                window.computer._history[window.surface].append({
                    "sequence": cursor._sequence, "session": cursor.session, "observation_id": snapshot.id,
                    "effect": result.get("effect", "unknown"),
                    "local_x": step.point.x*frame.width/frame.pixel_width,
                    "local_y": step.point.y*frame.height/frame.pixel_height})
        except ComputerError as exc:
            status, error = "stopped", exc.as_dict()
        finally:
            window.computer._latest.pop(window.surface, None)
            try:
                final = window._observe_current()
            except Exception as exc:
                error = {"code": "post_observation_failed", "message": str(exc), "prior_error": error}
                status = "unverified"
        return TimelineResult(status, records, final, time.monotonic()-epoch, error)
