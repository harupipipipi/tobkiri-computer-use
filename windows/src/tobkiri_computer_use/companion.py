"""Optional visual telemetry. Never carries text, tokens or input commands.

The companion is an independent renderer; delivery errors cannot change an input
result. Enable with Computer(companion=True) or TOBKIRI_COMPANION=1 for MCP.
"""
from contextlib import contextmanager
import json
import os
import socket
import sys
import threading
import time
import uuid


ACTIONS = {"click": "click", "double_click": "double_click", "right_click": "right_click",
           "type_text": "type", "set_value": "type", "press_key": "key", "hotkey": "key",
           "scroll": "scroll_down", "drag": "drag"}


def physical_point(point, window_id):
    """Convert the caller's Win32 virtualized frame to physical capture pixels.

    Do not alter the input API's calibrated coordinate contract. The Electron
    renderer alone needs physical coordinates; GetWindowRect otherwise returns
    96-DPI coordinates from a DPI-unaware Python process on a scaled display.
    """
    if sys.platform != "win32" or window_id is None:
        return tuple(point)
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    logical, physical = wintypes.RECT(), wintypes.RECT()
    if not user32.GetWindowRect(window_id, ctypes.byref(logical)):
        return tuple(point)
    set_context = user32.SetThreadDpiAwarenessContext
    set_context.argtypes = [ctypes.c_void_p]
    set_context.restype = ctypes.c_void_p
    previous = set_context(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2, this thread only
    if not previous:
        return tuple(point)
    try:
        if not user32.GetWindowRect(window_id, ctypes.byref(physical)):
            return tuple(point)
    finally:
        set_context(previous)
    width, height = logical.right - logical.left, logical.bottom - logical.top
    if width <= 0 or height <= 0:
        return tuple(point)
    return (physical.left + (point[0] - logical.left) * (physical.right - physical.left) / width,
            physical.top + (point[1] - logical.top) * (physical.bottom - physical.top) / height)


class CompanionPublisher:
    def __init__(self, enabled=None):
        self.enabled = os.environ.get("TOBKIRI_COMPANION") == "1" if enabled is None else bool(enabled)
        self.source = uuid.uuid4().hex
        self._socket = None
        self._seq = 0
        self._positions = {}
        self._guard = threading.RLock()
        self.error = None
        self.last_ready = False
        self.sync_error = None
        self.sync_elapsed_ms = 0
        self._address = None
        if self.enabled:
            try:
                port = int(os.environ.get("TOBKIRI_COMPANION_PORT", "47831"))
                if not 1024 < port < 65536:
                    raise ValueError("Companion port must be 1025..65535")
                self._address = ("127.0.0.1", port)
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                if hasattr(socket, "SIO_UDP_CONNRESET"):
                    # A renderer restart must not poison the next arrival wait
                    # with a delayed ICMP port-unreachable from an old heartbeat.
                    self._socket.ioctl(socket.SIO_UDP_CONNRESET, False)
                self._socket.setblocking(False)
            except (OSError, ValueError) as exc:
                self.error = str(exc)

    def status(self):
        return {"enabled": self.enabled, "transport": "loopback_udp", "error": self.error,
                "port": self._address[1] if self._address else None,
                "renderer_ready": self.last_ready, "sync_error": self.sync_error,
                "sync_elapsed_ms": self.sync_elapsed_ms, "delivery_verified": False}

    def _send(self, session, action, phase, point, outcome="unknown"):
        if not self._socket:
            return
        # Display metadata only; never sends actual input or application content.
        with self._guard:
            self._seq += 1
            event = {"version": 1, "source": self.source, "session": str(session or "default")[:160],
                     "seq": self._seq, "action": action, "phase": phase, "point": list(point),
                     "space": "physical" if sys.platform == "win32" else "dip", "outcome": outcome}
            try:
                self._socket.sendto(json.dumps(event, allow_nan=False).encode(), self._address)
                self.error = None
                return self._seq
            except (OSError, ValueError, TypeError) as exc:
                self.error = str(exc)

    def _prepare(self, session, action, point):
        """Wait for the visible character to arrive, never for permission/input.

        A missing renderer costs at most 60ms. A responding renderer has 1.2s to
        reach the point and pose. Timeout changes only presentation; input is
        dispatched exactly once by the original caller, never retried here.
        """
        self.last_ready = False
        self.sync_error = None
        if not self._socket or os.environ.get("TOBKIRI_COMPANION_SYNC") == "0":
            return
        with self._guard:
            seq = self._send(session, action, "prepare", point)
            if seq is None:
                return
            started = time.monotonic()
            deadline = started + .06
            try:
                while time.monotonic() < deadline:
                    self._socket.settimeout(max(.001, deadline - time.monotonic()))
                    try:
                        packet, address = self._socket.recvfrom(1024)
                    except ConnectionResetError:
                        # Windows queues ICMP errors from earlier sends while the
                        # renderer was absent. They do not describe this request.
                        continue
                    if address != self._address:
                        continue
                    try:
                        ack = json.loads(packet)
                    except (ValueError, UnicodeError):
                        continue
                    if not isinstance(ack, dict):
                        continue
                    if ack.get("source") != self.source or ack.get("seq") != seq:
                        continue
                    if ack.get("phase") == "accepted":
                        deadline = started + 1.26
                    elif ack.get("phase") == "ready":
                        self.last_ready = True
                        return
            except (OSError, ValueError, TypeError) as exc:
                self.sync_error = f"{type(exc).__name__}: {exc}"
            finally:
                self.sync_elapsed_ms = round((time.monotonic() - started) * 1000, 1)
                try:
                    self._socket.setblocking(False)
                except OSError:
                    pass

    def anchor(self, session, point, *, window_id=None):
        if not self.enabled:
            return
        try:
            point = physical_point(point, window_id)
        except (AttributeError, OSError, ValueError):
            self.error = "Could not map the companion to physical screen coordinates"
            return
        with self._guard:
            previous = self._positions.get(session)
            now = time.monotonic()
            point = tuple(point)
            if previous and previous[0] == point and now - previous[1] < .5:
                return
            self._positions[session] = (point, now)
            self._send(session, "move", "anchor", point)

    def hide(self, session):
        with self._guard:
            previous = self._positions.pop(session, None)
            if previous:
                self._send(session, "hide", "hide", previous[0])

    @contextmanager
    def action(self, session, name, arguments):
        with self._guard:
            previous = self._positions.get(session)
        action = ACTIONS.get(name)
        if not self.enabled or not previous or not action:
            yield {}
            return
        if name == "scroll" and arguments.get("direction") in ("up", "left"):
            action = "scroll_up"
        self._prepare(session, action, previous[0])
        self._send(session, action, "start", previous[0])
        receipt = {}
        try:
            yield receipt
        except BaseException:
            self._send(session, action, "end", previous[0], "error")
            raise
        else:
            raw = receipt.get("result") or {}
            data = raw.get("structuredContent", raw) if isinstance(raw, dict) else {}
            refused = isinstance(data, dict) and data.get("effect") == "refused"
            outcome = "error" if isinstance(raw, dict) and raw.get("isError") else "refused" if refused else "attempted"
            self._send(session, action, "end", previous[0], outcome)

    def close(self):
        with self._guard:
            for session in list(self._positions):
                self.hide(session)
            if self._socket:
                self._socket.close()
                self._socket = None
