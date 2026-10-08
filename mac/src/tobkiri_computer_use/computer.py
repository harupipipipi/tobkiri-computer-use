from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, nullcontext
import base64
import difflib
import hashlib
from io import BytesIO
import json
import math
import sys
import threading
import uuid

from PIL import Image
from .consent import ConsentRequest, InputCoordinator, require_consent, requires_consent
from .cursor import CursorFollower, RawCursorOwner, MOTION_PROFILES
from .companion import CompanionPublisher
from .geometry import Frame, segment_intersects_rect
from .models import Element, Observation, Point
from .transport import ComputerError, McpTransport, structured


class Computer:
    """One persistent driver connection. Always use as a context manager.

    The complete upstream tool surface remains available through tool().
    window() and mouse() add bounded observations and safe coordinate handling.
    """
    def __init__(self, *, command=None, transport=None, cursor_coordinates=None, approval_callback=None, cursor_follow_interval=0.1, cursor_profile="fast", companion=None):
        if cursor_profile not in (None, *MOTION_PROFILES):
            raise ValueError("cursor_profile must be fast, normal, or None (native settings)")
        self.cursor_profile = cursor_profile
        if cursor_coordinates not in (None, "screen_points", "window_pixels"):
            raise ValueError("cursor_coordinates must be screen_points or window_pixels")
        if cursor_follow_interval is not None and not .02 <= cursor_follow_interval <= 5:
            raise ValueError("cursor_follow_interval must be .02..5 seconds, or None for manual updates")
        self.transport = transport or McpTransport(command)
        self._guard = threading.RLock()
        self._input_lock = threading.RLock()
        self._inputs = InputCoordinator()
        self._approval_callback = approval_callback
        self._locks = {}
        self._latest = {}
        self._sessions = set()
        self._history = {}
        self._pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tobkiri-mouse")
        self._closed = False
        self._companion = CompanionPublisher(companion)
        self._cursors = CursorFollower(self, cursor_follow_interval)
        self._raw_views = {}
        self._raw_owners = {}
        # Measured on macOS cua-driver 0.28.2: move_cursor ignores target's
        # pixel transform and consumes global screen points. Do NOT generalize
        # this workaround to unknown driver builds.
        version = self.transport.server_info.get("version", "")
        self.cursor_coordinates = cursor_coordinates or (
            "screen_points" if sys.platform == "darwin" and version == "0.28.2" else None)

    def tool(self, name, arguments=None):
        """Call an unchanged upstream Cua tool. Manage its snapshots yourself.

        Raw calls preserve Cua's tool surface. Only observations affected by a
        mutation or native snapshot refresh are invalidated.
        """
        # Copy now: a caller cannot change the reviewed action while approval
        # waits. Raw calls stay schema-compatible but share the consent boundary.
        arguments = json.loads(json.dumps(arguments or {}, allow_nan=False))
        with self._inputs.hold(exclusive=True), self._guard, ExitStack() as stack:
            for key in sorted(self._locks):
                stack.enter_context(self._locks[key])
            self._invalidate_raw(name, arguments)
            try:
                arguments = self._refresh_raw_input(name, arguments)
                browser_setup = self._browser_setup_changes_ui(name, arguments)
                if requires_consent(name, arguments) or browser_setup:
                    request = ConsentRequest.create(name, {"native_arguments": arguments},
                                                    "Browser setup may change remote-debugging settings and use foreground input"
                                                    if browser_setup else "Explicit low-level foreground/desktop operation")
                    require_consent(self._approval_callback, request)
                    arguments = self._refresh_raw_input(name, arguments)
                with self._companion.action(arguments.get("session"), name, arguments) as receipt:
                    result = self.transport.call(name, arguments)
                    receipt["result"] = result
                self._follow_raw_cursor(name, arguments, result)
                return result
            finally:
                self._invalidate_raw(name, arguments)

    def _invalidate_raw(self, name, args):
        # Read-only metadata and browser snapshots do not replace native AX
        # tokens. Virtual overlays and window translation also leave them valid.
        if name in {"list_windows", "list_apps", "list_sessions", "get_config",
                    "get_browser_state", "get_agent_cursor_state", "get_cursor_position",
                    "get_screen_size", "get_session", "get_session_state", "get_recording_state",
                    "check_permissions", "check_for_update", "health_report", "clipboard_read",
                    "get_desktop_state", "get_accessibility_tree", "set_agent_cursor_enabled",
                    "set_agent_cursor_motion", "set_agent_cursor_theme", "start_session",
                    "set_window_frame"}:
            return
        if name == "move_cursor" and not requires_consent(name, args):
            return
        if name == "page" and args.get("action") in {"get_text", "query_dom"}:
            return
        target = args.get("target") or args
        surface = (target.get("pid"), target.get("window_id"))
        if None not in surface:
            self._latest.pop(surface, None)
        elif target.get("pid") is not None:
            for key in list(self._latest):
                if key[0] == target["pid"]:
                    self._latest.pop(key, None)
        else:
            # Unknown mutations can affect several windows. Do not guess scope.
            self._latest.clear()

    def _browser_setup_changes_ui(self, name, args):
        if name != "browser_prepare" or args.get("strategy", {}).get("kind") != "existing_profile":
            return False
        if "pid" not in args or "window_id" not in args:
            return False  # Let the native schema reject an incomplete request.
        # Bind can report browser_consent_required before checking whether an
        # endpoint exists. Probe the non-acting prepare path instead: no strategy,
        # no profile and allow_launch=false can only discover an existing endpoint.
        probe = structured(self.transport.call("browser_prepare", {
            **{k: args[k] for k in ("pid", "session") if k in args}, "allow_launch": False}))
        return not (probe.get("status") == "ok" and probe.get("prepared") is True
                    and probe.get("action") == "already_prepared")

    def browser(self, *, pid, window_id):
        from .browser import Browser
        with self._guard:
            if self._closed:
                raise ComputerError("closed", "Computer is closed.")
            return Browser(self, pid, window_id)

    def _refresh_raw_input(self, name, args):
        if name not in ("click", "double_click", "right_click", "drag", "scroll", "type_text", "press_key", "hotkey"):
            return args
        if args.get("scope") == "desktop" or (args.get("target") or {}).get("kind") == "desktop":
            return args
        target = args.get("target") or args
        surface = (target.get("pid"), target.get("window_id"))
        if surface not in self._raw_views:
            return args  # Native driver still validates unobserved/foreign tokens.
        frame, old, options = self._raw_views[surface]
        rows = self.windows(pid=surface[0])
        matches = [r for r in rows if r.get("window_id") == surface[1]]
        if len(matches) != 1:
            raise ComputerError("stale_geometry", "The observed window is unavailable.")
        live = frame.at_bounds(matches[0].get("bounds", {}))
        if not frame.same_size(live):
            raise ComputerError("stale_geometry", "The window resized; capture its new image before input.")
        if abs(frame.x-live.x) <= .5 and abs(frame.y-live.y) <= .5:
            return args
        if args.get("from_zoom"):
            raise ComputerError("stale_geometry", "Refresh this legacy driver zoom after a move, or use tobkiri_zoom's bound crop.")
        element = None
        if "element_token" in args or "element_index" in args:
            element = next((e for e in old.get("elements", []) if ("element_token" in args and e.get("element_token") == args["element_token"])
                            or (e.get("element_index") == args.get("element_index") and old.get("snapshot_id") == args.get("snapshot_id"))), None)
            if element is None:
                raise ComputerError("stale_observation", "The supplied element was not in this window's recorded snapshot.")
        raw = structured(self.transport.call("get_window_state", options))
        b = raw.get("window_bounds", {})
        fresh = Frame(*(b[k] for k in ("x", "y", "width", "height")), raw.get("screenshot_width", 0), raw.get("screenshot_height", 0))
        if (raw.get("pid"), raw.get("window_id")) != surface or not raw.get("screenshot_frame_valid", True) or not frame.same_size(fresh) or Window._layout_raw(old) != Window._layout_raw(raw):
            self._raw_views.pop(surface, None)
            raise ComputerError("stale_geometry", "Image scale or window layout changed; observe again before input.")
        self._raw_views[surface] = (fresh, raw, options)
        if element is not None:
            new = next(e for e in raw["elements"] if e["element_index"] == element["element_index"])
            args = {k: v for k, v in args.items() if k not in ("element_token", "element_index", "snapshot_id")}
            args.update(element_token=new["element_token"])
        return args

    def _follow_raw_cursor(self, name, args, result):
        """Native RPC payload stays untouched; only its visual overlay is bound."""
        if name == "move_cursor" and args.get("cursor_id", "default") != "default":
            # This tracker owns one default overlay per session. A raw custom
            # cursor must not accidentally re-anchor that session's default.
            return
        session = args.get("session")
        if name == "end_session" or (name == "set_agent_cursor_enabled" and args.get("enabled") is False):
            self._cursors.forget(session)
            self._raw_owners.pop(session, None)
            return
        if args.get("scope") == "desktop" or (args.get("target") or {}).get("kind") == "desktop":
            self._cursors.forget(session)
            return
        raw = structured(result)
        if name == "get_window_state" and raw.get("window_bounds") and raw.get("screenshot_width") and raw.get("screenshot_height") and raw.get("screenshot_frame_valid", True):
            surface = (raw.get("pid"), raw.get("window_id"))
            b = raw["window_bounds"]
            frame = Frame(b["x"], b["y"], b["width"], b["height"], raw["screenshot_width"], raw["screenshot_height"])
            self._raw_views[surface] = (frame, raw, dict(args))
        else:
            target = args.get("target") or args
            surface = (target.get("pid"), target.get("window_id"))
            if name not in ("click", "double_click", "right_click", "drag", "scroll", "type_text", "press_key", "hotkey", "move_cursor") or surface not in self._raw_views:
                return
            frame, raw, _ = self._raw_views[surface]
        if None in surface or self.cursor_coordinates is None:
            return
        owner = self._raw_owners.get(session)
        if owner is None or owner.surface != surface:
            self._cursors.forget(session)
            owner = RawCursorOwner(self, surface, session, self._locks.setdefault(surface, threading.RLock()))
            self._raw_owners[session] = owner
        point = None
        if name == "move_cursor":
            # Native 0.28.2 move_cursor takes screen points; do not reinterpret
            # its raw contract as helper screenshot pixels.
            point = frame.from_screen(args["x"], args["y"]) if self.cursor_coordinates == "screen_points" else (args["x"], args["y"])
        elif all(k in args for k in ("x", "y")):
            point = (args["x"], args["y"])
        elif name == "drag":
            point = (args["to_x"], args["to_y"])
        elif "element_token" in args or "element_index" in args:
            element = next((e for e in raw.get("elements", []) if ("element_token" in args and e.get("element_token") == args["element_token"])
                            or ("element_index" in args and e.get("element_index") == args["element_index"])), None)
            if element and element.get("frame"):
                point = frame.element_center(element["frame"])
        elif not self._cursors.has(owner):
            point = (frame.pixel_width/2, frame.pixel_height/2)
        if point is not None:
            try:
                with owner._lock:
                    self._cursors.bind(owner, frame, *point)
            except Exception:
                # A visual failure must not masquerade as an input failure and
                # encourage a duplicate click. The original result is preserved;
                # cursor status carries the overlay error.
                pass

    def companion_status(self):
        """Local renderer telemetry status; not evidence of input success."""
        return self._companion.status()

    def cursor_status(self, *, pid=None, window_id=None):
        owners = list(self._raw_owners.values())
        owners.extend(a.owner for a in self._cursor_anchors())
        seen, result = set(), []
        for owner in owners:
            if owner.session in seen or (pid is not None and owner.surface[0] != pid) or (window_id is not None and owner.surface[1] != window_id):
                continue
            seen.add(owner.session)
            result.append({"session": owner.session, **self._cursors.status(owner)})
        return result

    def _cursor_anchors(self):
        with self._cursors._guard:
            return list(self._cursors._anchors.values())

    def list_tools(self):
        return self.transport.list_tools()

    def windows(self, *, app=None, title=None, pid=None):
        args = {"pid": pid} if pid is not None else {}
        rows = structured(self.transport.call("list_windows", args)).get("windows", [])
        return [r for r in rows if (app is None or r.get("app_name", "").casefold() == app.casefold())
                and (title is None or r.get("title") == title)]

    def window(self, *, pid=None, window_id=None, app=None, title=None, name="computer"):
        if pid is None or window_id is None:
            matches = self.windows(app=app, title=title, pid=pid)
            if window_id is not None:
                matches = [m for m in matches if m["window_id"] == window_id]
            if len(matches) != 1:
                raise ComputerError("ambiguous_window", "Select an exact window by pid/window_id or unique app/title.", details=matches)
            pid, window_id = matches[0]["pid"], matches[0]["window_id"]
        if not isinstance(pid, int) or not isinstance(window_id, int) or pid <= 0 or window_id < 0:
            raise ComputerError("invalid_target", "pid/window_id must identify a native window.")
        with self._guard:
            if self._closed:
                raise ComputerError("closed", "Computer is closed.")
            key = (pid, window_id)
            lock = self._locks.setdefault(key, threading.RLock())
            self._history.setdefault(key, deque(maxlen=32))
            session = f"{name[:32]}-{uuid.uuid4().hex[:12]}"
            self.transport.call("start_session", {"session": session})
            self._sessions.add(session)
            self.transport.call("set_agent_cursor_enabled", {"session": session, "enabled": False})
        window = Window(self, key, session, lock)
        if self.cursor_profile:
            window.set_cursor_speed(self.cursor_profile)
        return window

    def mouse(self, name, *, pid, window_id):
        """Independent visible cursor and ordered input stream on an exact window."""
        return self.window(pid=pid, window_id=window_id, name=name)

    def parallel(self, *jobs):
        """Run independent jobs; join all and return results/errors in input order.

        A shared window is serialized. Native keyboard delivery can be per-PID
        and may refuse same-app ambiguity; no automatic foreground fallback.
        """
        futures = [self._pool.submit(job) for job in jobs]
        results = []
        for future in futures:
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(exc)
        return results

    def close(self):
        if self._closed:
            return
        self._pool.shutdown(wait=True, cancel_futures=False)
        self._cursors.close()
        self._companion.close()
        self._closed = True
        for session in list(self._sessions):
            try:
                self.transport.call("end_session", {"session": session})
            except ComputerError:
                pass
        self._sessions.clear()
        self.transport.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Window:
    def __init__(self, computer, surface, session, lock):
        self.computer, self.surface, self.session, self._lock = computer, surface, session, lock
        self._last = None
        self._closed = False
        self._sequence = 0

    @property
    def target(self):
        return {"kind": "window", "pid": self.surface[0], "window_id": self.surface[1]}

    def _call(self, name, **args):
        if self._closed or self.computer._closed:
            raise ComputerError("closed", "This window session is closed.")
        with self.computer._companion.action(self.session, name, args) as receipt:
            result = self.computer.transport.call(name, {"session": self.session, **args})
            receipt["result"] = result
            return result

    def set_cursor_speed(self, profile="fast"):
        """Configure only this session's virtual overlay. Does not take focus.

        Native acknowledgement queues the change; it becomes visible on a render
        tick. Use get_agent_cursor_state to inspect the eventual readback.
        """
        if profile not in MOTION_PROFILES:
            raise ValueError("profile must be fast or normal")
        with self._lock:
            return structured(self._call("set_agent_cursor_motion", **MOTION_PROFILES[profile]))

    def timeline(self, steps, *, start_at=None, max_lateness=.25, on_late="stop", stop_event=None):
        """Run a bounded, pre-observed sequence of background clicks on a static UI.

        Times use time.monotonic(). Different named cursors may share this exact
        window; input is serialized. Use Computer.parallel for different windows.
        """
        from .timeline import run_timeline
        return run_timeline(self, steps, start_at=start_at, max_lateness=max_lateness, on_late=on_late, stop_event=stop_event)

    def locator(self, label=None, *, role=None, contains=False):
        """Reusable semantic selector, resolved from a fresh observation per action."""
        from .automation import Locator
        return Locator(self, label, role=role, contains=contains)

    def wait_for(self, predicate, *, timeout=5, poll_interval=.25, stop_event=None):
        """Observe until a read-only predicate is true; never retry an input.

        Returns the matching Observation. Cancellation/deadline errors retain
        read evidence. A native observation has its own transport timeout.
        """
        from .automation import wait_for
        return wait_for(self, predicate, timeout=timeout, poll_interval=poll_interval, stop_event=stop_event)

    def observe(self, *, screenshot=True, max_dimension=1400, max_elements=2000, full_tree=False):
        return self._observe(screenshot=screenshot, max_dimension=max_dimension,
                             max_elements=max_elements, full_tree=full_tree)

    def _observe_current(self):
        """Automatic readback keeps the caller's image scale and AX walk budget."""
        return self.observe(**getattr(self, "_last_options", {}))

    def _observe(self, *, screenshot=True, max_dimension=1400, max_elements=2000, full_tree=False, translation_from=None):
        with self._lock:
            result = self._call("get_window_state", pid=self.surface[0], window_id=self.surface[1],
                                include_screenshot=screenshot, max_dimension=max_dimension, max_elements=max_elements)
            raw = structured(result)
            if (raw.get("pid"), raw.get("window_id")) != self.surface:
                raise ComputerError("target_mismatch", "Driver returned a different window; input was not sent.")
            image = next((base64.b64decode(b["data"]) for b in result.get("content", []) if b.get("type") == "image"), None)
            frame = None
            bounds = raw.get("window_bounds")
            if image and bounds and raw.get("screenshot_frame_valid", True):
                size = Image.open(BytesIO(image)).size
                if size != (raw.get("screenshot_width"), raw.get("screenshot_height")):
                    raise ComputerError("invalid_frame", "Image dimensions disagree with driver metadata.")
                frame = Frame(bounds["x"], bounds["y"], bounds["width"], bounds["height"], *size)
            observation_id = translation_from.id if translation_from else "o_" + uuid.uuid4().hex
            elements = []
            blocked = set()
            for e in raw.get("elements", []):
                index = e["element_index"]
                if not full_tree and (e.get("role") in ("AXMenuBar", "AXMenuBarItem", "AXMenu", "AXMenuItem") or e.get("parent_index") in blocked):
                    blocked.add(index)
                    continue
                center = None
                if frame and e.get("frame") and sys.platform == "darwin":
                    center = frame.element_center(e["frame"])
                point = Point(*center, observation_id, self.surface) if center else None
                elements.append(Element(index, e.get("role", ""), e.get("label", ""), e.get("value"),
                                        e.get("element_token"), observation_id, self.surface, point, e))
            tree = raw.get("tree_markdown", "")
            if not full_tree:
                tree = tree.split(" AXMenuBar", 1)[0]
                # Remove the partial menu-line prefix left by the split.
                tree = tree.rsplit("\n", 1)[0] if " AXMenuBar" in raw.get("tree_markdown", "") else tree
            old = self._last
            changes = tree if old is None else "\n".join(difflib.unified_diff(
                old.tree.splitlines(), tree.splitlines(), fromfile="before", tofile="after", lineterm="")) or "No accessibility change."
            history = self.computer._history[self.surface]
            if frame and old and old.frame and (frame.width, frame.height) != (old.frame.width, old.frame.height):
                history.clear()
            marks = tuple({**m, "x": m["local_x"]*frame.pixel_width/frame.width,
                            "y": m["local_y"]*frame.pixel_height/frame.height} for m in history) if frame else ()
            snapshot = Observation(observation_id, self.surface, raw.get("snapshot_id", ""), frame,
                                   tuple(elements), tree, image, raw, changes, marks)
            if translation_from and (not frame or not translation_from.frame.same_size(frame)
                                     or self._layout(translation_from) != self._layout(snapshot)):
                self.computer._latest.pop(self.surface, None)
                raise ComputerError("stale_geometry", "Window size, image scale or element layout changed; observe again before input.")
            self._last = snapshot
            self._last_options = {"screenshot": screenshot, "max_dimension": max_dimension,
                                  "max_elements": max_elements, "full_tree": full_tree}
            self.computer._latest[self.surface] = snapshot.id
            if frame and not self.computer._cursors.has(self) and self.computer.cursor_coordinates is not None:
                self._bind_cursor(snapshot, snapshot.point(frame.pixel_width/2, frame.pixel_height/2))
            snapshot.cursor = self.computer._cursors.status(self)
            return snapshot

    @staticmethod
    def _layout(observation):
        return Window._layout_raw({**observation.raw, "elements": [e.raw for e in observation.elements]})

    @staticmethod
    def _layout_raw(raw):
        """Compare semantic identity and WINDOW-LOCAL geometry, not screen origin."""
        b = raw["window_bounds"]
        result = []
        blocked = set()
        for e in raw.get("elements", []):
            if e.get("role") in ("AXMenuBar", "AXMenuBarItem", "AXMenu", "AXMenuItem") or e.get("parent_index") in blocked:
                blocked.add(e["element_index"])
                continue
            r = e.get("frame")
            local = tuple(round(v, 1) for v in (r["x"]-b["x"], r["y"]-b["y"], r["w"], r["h"])) if r else None
            result.append((e["element_index"], e.get("role"), e.get("label"), e.get("enabled"), local))
        return result

    def _fresh(self, target):
        if target.surface != self.surface or target.observation_id != self.computer._latest.get(self.surface):
            raise ComputerError("stale_observation", "Observe this exact window again and use its new element/point.")
        if not self._last or target.observation_id != self._last.id:
            raise ComputerError("stale_observation", "This point belongs to another cursor's observation; observe with this cursor.")
        return self._last

    def _check_geometry(self, observation, *, refresh=True):
        windows = self.computer.windows(pid=self.surface[0])
        matches = [w for w in windows if w.get("window_id") == self.surface[1]]
        if len(matches) != 1 or not observation.frame:
            raise ComputerError("stale_geometry", "Window/capture is unavailable; observe again.")
        old_title, live_title = observation.raw.get("window_title"), matches[0].get("title")
        if old_title and live_title and old_title != live_title:
            self.computer._latest.pop(self.surface, None)
            raise ComputerError("stale_observation", "The window title/page changed since observation; inspect the current page before input.")
        b, f = matches[0].get("bounds", {}), observation.frame
        current = f.at_bounds(b)
        if not f.same_size(current):
            self.computer._latest.pop(self.surface, None)
            raise ComputerError("stale_geometry", "Window resized; observe again before pixel input.")
        if refresh and (abs(f.x-current.x) > .5 or abs(f.y-current.y) > .5):
            self._observe(**self._last_options, translation_from=observation)
        return windows

    def _check_pointer_target(self, observation, points, *, delivery_mode="background"):
        windows = self._check_geometry(observation)
        observation = self._last if self._last and self._last.id == observation.id else observation
        if delivery_mode != "background":
            return
        # macOS PID-routed pixel input can be hit-tested against another window
        # of the SAME process. An exact capture id alone does not prove input
        # isolation. Refuse overlapping siblings; a semantic element is safer.
        positions = [observation.frame.to_screen(p.x, p.y) for p in points]
        for row in windows:
            if row.get("window_id") == self.surface[1] or row.get("is_on_screen") is False or row.get("on_current_space") is False:
                continue
            rect = row.get("bounds", {})
            if not all(k in rect for k in ("x", "y", "width", "height")) or rect["width"] <= 0 or rect["height"] <= 0:
                continue
            segments = list(zip(positions, positions[1:])) or [(positions[0], positions[0])]
            if any(segment_intersects_rect(start, end, rect) for start, end in segments):
                raise ComputerError("overlapping_window", "Another window of this app covers the input point/path. Use a fresh semantic element instead of pixel input.",
                                    details={"target_window_id": self.surface[1], "overlapping_window_id": row["window_id"]})

    def _check_keyboard_target(self, observation, delivery_mode):
        if delivery_mode != "background":
            return
        info = observation.raw.get("background_input", {})
        route = next((r for r in info.get("routes", []) if r.get("route") == "pid_keyboard"), {})
        if route.get("status") != "available":
            raise ComputerError("keyboard_target_unproven", "Background keyboard routing to this exact window is not proven. Use set_value on a native field or an exact browser-tab tool.",
                                details={"target": self.target, "route": route})

    def _approve_foreground(self, action, address, before, arguments, reason):
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise ComputerError("fallback_reason_required", "Explain why background input is insufficient before requesting this one foreground action.")
        if not before.frame:
            raise ComputerError("no_pixel_frame", "Observe with a screenshot before requesting foreground input.")
        self._check_geometry(before)
        request = ConsentRequest.create(action, {
            "target": self.target, "window_title": before.raw.get("window_title"),
            "observation_id": before.id, "window_bounds": before.raw.get("window_bounds"),
            "elements": [e.to_dict() for e in before.elements
                         if e.token == address.get("element_token") or e.id == address.get("element_index")],
            "native_arguments": {**address, **arguments},
        }, reason.strip())
        try:
            receipt = require_consent(self.computer._approval_callback, request)
        except Exception:
            # Even a denied/expired dialog may have outlived the observation.
            self.computer._latest.pop(self.surface, None)
            raise
        # A human may take a minute to answer. Re-capture with the SAME scale,
        # then reject moved/changed targets instead of applying an old approval
        # to a new screen. Token refresh is allowed only for identical content.
        fresh = self.observe(**self._last_options)
        def fingerprint(observation):
            elements = [{k: v for k, v in e.raw.items() if k not in ("element_token", "snapshot_id")}
                        for e in observation.elements]
            return (observation.raw.get("window_title"), observation.frame, elements)
        pixels = any(k in address for k in ("x", "from_x"))
        if (fingerprint(before) != fingerprint(fresh)
                or (pixels and hashlib.sha256(before.image).digest() != hashlib.sha256(fresh.image or b"").digest())):
            raise ComputerError("approval_target_changed", "The window changed while approval was pending. No input was sent. Inspect the new observation and request a new approval.",
                                details={"request_id": request.id, "observation_id": fresh.id})
        self._check_geometry(fresh)
        if "element_token" in address or "element_index" in address:
            original = next(e for e in before.elements
                            if e.token == address.get("element_token") or e.id == address.get("element_index"))
            address, _, _ = self._address(fresh.element(original.id))
        return address, fresh, receipt

    def _address(self, target):
        if isinstance(target, str):
            target = self._observe_current().find(target)
        if not isinstance(target, (Element, Point)):
            raise ComputerError("invalid_target", "Use a label, fresh Element, or observation.point(x,y).")
        snapshot = self._fresh(target)
        if snapshot.frame:
            self._check_geometry(snapshot)
            snapshot = self._last
        if isinstance(target, Element):
            # A translation can refresh the native token without changing the
            # model's logical observation id or window-relative coordinates.
            target = snapshot.element(target.id)
            if target.raw.get("enabled") is False:
                raise ComputerError("element_disabled", "The selected element is disabled.")
            # Never allow global menus or clearly out-of-window AX elements to
            # sneak through an otherwise exact-window helper.
            if target.role in ("AXMenuBar", "AXMenuBarItem", "AXMenu", "AXMenuItem"):
                raise ComputerError("outside_window", "Use the native menu tool for application-global menus.")
            if sys.platform == "darwin" and target.raw.get("frame") and snapshot.raw.get("window_bounds"):
                bounds = snapshot.raw["window_bounds"]
                frame = Frame(bounds["x"], bounds["y"], bounds["width"], bounds["height"], 1, 1)
                if frame.element_center(target.raw["frame"]) is None:
                    raise ComputerError("outside_window", "Element is outside the selected window; observe or scroll to it first.")
            args = {"pid": self.surface[0], "window_id": self.surface[1]}
            if target.token:
                args["element_token"] = target.token
            elif snapshot.driver_snapshot_id:
                args.update(element_index=target.id, snapshot_id=snapshot.driver_snapshot_id)
            else:
                raise ComputerError("missing_snapshot", "Driver did not return a snapshot-bound element handle.")
            return args, target.point, snapshot
        if not snapshot.frame:
            raise ComputerError("no_pixel_frame", "Observe with a screenshot before pixel input.")
        snapshot.frame.check_pixel(target.x, target.y)
        return {"target": self.target, "x": target.x, "y": target.y}, target, snapshot

    def _perform(self, action, target=None, *, expect=None, fallback_reason=None, **arguments):
        arguments = json.loads(json.dumps(arguments, allow_nan=False))
        delivery = arguments.get("delivery_mode", "background")
        if delivery not in ("background", "foreground"):
            raise ComputerError("invalid_delivery_mode", "Use background or explicitly approved foreground input.")
        # Foreground/global input shares an OS keyboard/pointer. Never run those
        # concurrently, even when the high-level jobs address different windows.
        input_lock = self.computer._input_lock if delivery == "foreground" or action in ("type_text", "press_key") else nullcontext()
        with self.computer._inputs.hold(exclusive=delivery == "foreground"), input_lock, self._lock:
            if target is not None:
                address, point, before = self._address(target)
            else:
                before = self._observe_current()
                address, point = {"pid": self.surface[0], "window_id": self.surface[1]}, None
            if action in ("double_click", "right_click") and "target" in address:
                address = {k: v for k, v in address.items() if k != "target"}
                address.update(pid=self.surface[0], window_id=self.surface[1])
            if action in ("type_text", "press_key"):
                self._check_keyboard_target(before, delivery)
            semantic_press = action == "click" and any(
                e.token == address.get("element_token") and "AXPress" in e.raw.get("actions", [])
                for e in before.elements if e.token)
            pointer_action = action in ("click", "double_click", "right_click", "scroll") and not semantic_press
            if pointer_action or ("x" in address and "y" in address):
                if point is None or before.frame is None:
                    raise ComputerError("no_pixel_frame", "This input may use pointer events; a visible, measured target is required.")
                self._check_pointer_target(before, [point], delivery_mode=delivery)
                # A second live bounds read may have refreshed native tokens.
                if target is not None and self._last is not before:
                    address, point, before = self._address(target)
            approval = None
            if delivery == "foreground":
                address, before, approval = self._approve_foreground(action, address, before, arguments, fallback_reason)
            if action in ("double_click", "right_click") and "target" in address:
                address = {k: v for k, v in address.items() if k != "target"}
                address.update(pid=self.surface[0], window_id=self.surface[1])
            if point and before.frame:
                # Explicit AX clicks animate inside Cua. Pixel clicks can take
                # Cua's early AX hit-test return, which skips its cursor update;
                # retain one fast pre-move for those so visuals stay synchronized.
                self._bind_cursor(before, point, drive="x" in address or action not in ("click", "double_click", "right_click"))
                if self.computer._latest.get(self.surface) != before.id:
                    raise ComputerError("stale_geometry", "The window resized or disappeared immediately before input; observe again.")
            self.computer._latest.pop(self.surface, None)
            raw_result = self._call(action, **address, **arguments)
            delivery_result = structured(raw_result)
            if action in ("click", "double_click", "right_click") and point and before.frame and delivery_result.get("effect") != "refused":
                self._sequence += 1
                f = before.frame
                self.computer._history[self.surface].append({
                    "sequence": self._sequence, "session": self.session,
                    "observation_id": before.id, "effect": delivery_result.get("effect", "unknown"),
                    "local_x": point.x*f.width/f.pixel_width, "local_y": point.y*f.height/f.pixel_height,
                })
            verification = None
            if expect is not None:
                verification = structured(self._call("verify_state", pid=self.surface[0], window_id=self.surface[1],
                                                     expect=expect, timeout_ms=5000, stable_samples=2))
            # Even a refused or unverifiable delivery returns current evidence.
            # Never replay input on a timeout or an unchanged tree.
            try:
                after = self._observe_current()
            except Exception as exc:
                raise ComputerError("post_observation_failed", "Action was attempted but its post-observation failed; do not retry blindly.",
                                    details={"delivery": delivery_result, "error": str(exc)}) from exc
            return ActionResult(action, delivery_result, after, verification, approval)

    def click(self, target, *, button="left", double=False, expect=None, delivery_mode="background", fallback_reason=None):
        if button not in ("left", "right") or (double and button != "left"):
            raise ComputerError("unsupported_click", "Use raw Cua tools for this click variant.")
        name = "double_click" if double else "right_click" if button == "right" else "click"
        return self._perform(name, target, expect=expect, delivery_mode=delivery_mode, fallback_reason=fallback_reason)

    def set_value(self, target, value, *, expect=None):
        if isinstance(target, Point):
            raise ComputerError("invalid_target", "set_value requires a semantic element; use type_text for pixels.")
        return self._perform("set_value", target, value=str(value), expect=expect)

    def type_text(self, target, text, *, expect=None, delivery_mode="background", fallback_reason=None):
        return self._perform("type_text", target, text=text, expect=expect, delivery_mode=delivery_mode, fallback_reason=fallback_reason)

    def press_key(self, key, *, target=None, modifiers=None, expect=None, delivery_mode="background", fallback_reason=None):
        return self._perform("press_key", target, key=key, modifiers=modifiers or [], expect=expect, delivery_mode=delivery_mode, fallback_reason=fallback_reason)

    def scroll(self, target, direction, *, amount=3, by="line", expect=None, delivery_mode="background", fallback_reason=None):
        return self._perform("scroll", target, direction=direction, amount=amount, by=by, expect=expect,
                             delivery_mode=delivery_mode, fallback_reason=fallback_reason)

    def drag(self, start: Point, end: Point, *, duration_ms=500, expect=None, delivery_mode="background", fallback_reason=None):
        if delivery_mode not in ("background", "foreground"):
            raise ComputerError("invalid_delivery_mode", "Use background or explicitly approved foreground input.")
        with self.computer._inputs.hold(exclusive=delivery_mode == "foreground"), self._lock:
            if not isinstance(start, Point) or not isinstance(end, Point):
                raise ComputerError("invalid_target", "drag requires two snapshot-bound points.")
            snapshot = self._fresh(start)
            self._fresh(end)
            # Check the whole path, not just endpoints: a sibling can intersect
            # the middle of a drag and receive a mouse-up.
            self._check_pointer_target(snapshot, [start, end], delivery_mode=delivery_mode)
            snapshot = self._last
            snapshot.frame.check_pixel(start.x, start.y)
            snapshot.frame.check_pixel(end.x, end.y)
            # _perform has no element target, so use a direct ordered gesture
            # without reobserving between the validation and dispatch.
            address = dict(target=self.target, from_x=start.x, from_y=start.y, to_x=end.x, to_y=end.y)
            arguments = dict(duration_ms=duration_ms, delivery_mode=delivery_mode)
            approval = None
            if delivery_mode == "foreground":
                address, snapshot, approval = self._approve_foreground("drag", address, snapshot, arguments, fallback_reason)
            self._bind_cursor(snapshot, start)
            if self.computer._latest.get(self.surface) != snapshot.id:
                raise ComputerError("stale_geometry", "The window changed immediately before the drag; observe again.")
            self.computer._latest.pop(self.surface, None)
            result = structured(self._call("drag", **address, **arguments))
            self._bind_cursor(snapshot, end)
            verification = self.verify(expect) if expect else None
            return ActionResult("drag", result, self._observe_current(), verification, approval)

    def verify(self, expect, *, timeout_ms=5000):
        with self._lock:
            self.computer._latest.pop(self.surface, None)
            return structured(self._call("verify_state", pid=self.surface[0], window_id=self.surface[1],
                                         expect=expect, timeout_ms=timeout_ms, stable_samples=2))

    def move(self, target):
        with self._lock:
            _, point, snapshot = self._address(target)
            if not point or not snapshot.frame:
                raise ComputerError("no_pixel_frame", "Cursor movement needs a visible, measured element center.")
            screen_x, screen_y = snapshot.frame.to_screen(point.x, point.y)
            mode = self.computer.cursor_coordinates
            if mode is None:
                raise ComputerError("cursor_contract_unknown", "Driver cursor coordinates are unverified for this build. Set cursor_coordinates only after calibration.")
            follow = self.computer._cursors.bind(self, snapshot.frame, point.x, point.y)
            if follow["phase"] != "following":
                raise ComputerError("cursor_unavailable", "The window cursor cannot be shown in this geometry/Space.", details=follow)
            screen_x, screen_y = follow["screen_point"]
            if self.computer._companion.enabled:
                # The character renderer replaces the deliberately disabled native marker.
                return {"expected_screen_point": [screen_x, screen_y], "reported_position": None,
                        "position_matches": None, "error_points": None, "visual_state": None,
                        "pixels_verified": False, "follow": follow,
                        "companion": self.computer.companion_status()}
            state = structured(self._call("get_agent_cursor_state"))
            position = state.get("position", {})
            error = math.hypot(position.get("x", math.inf)-screen_x, position.get("y", math.inf)-screen_y)
            return {"expected_screen_point": [screen_x, screen_y], "reported_position": position,
                    "position_matches": error <= 2, "error_points": error if math.isfinite(error) else None,
                    "visual_state": state.get("visual_state"), "pixels_verified": False, "follow": follow}

    def _bind_cursor(self, observation, point, *, drive=True):
        try:
            self.computer._cursors.bind(self, observation.frame, point.x, point.y, drive=drive)
        except Exception:
            pass  # Visual diagnostics are reported separately from input delivery.

    def move_async(self, target):
        """Return a Future; call result() to surface errors. No silent fire-and-forget."""
        return self.computer._pool.submit(self.move, target)

    def clear_marks(self):
        with self._lock:
            self.computer._history[self.surface].clear()

    def close(self):
        with self._lock:
            if not self._closed:
                self.computer._cursors.forget(self.session)
                self._call("end_session")
                self.computer._sessions.discard(self.session)
                self._closed = True


class ActionResult:
    def __init__(self, action, delivery, observation, verification=None, approval=None):
        self.action, self.delivery, self.observation, self.verification = action, delivery, observation, verification
        self.approval = approval

    def to_dict(self):
        return {"action": self.action, "delivery": self.delivery, "verification": self.verification, "approval": self.approval,
                "observation": self.observation.to_dict(diff=True)}
