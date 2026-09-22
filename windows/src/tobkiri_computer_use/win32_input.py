"""Consent-gated Win32 pointer fallback for Cua Driver 0.28.2."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import math
import time

from .transport import ComputerError


INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
SW_RESTORE = 9
ULONG_PTR = getattr(wintypes, "ULONG_PTR", wintypes.WPARAM)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _user32():
    if not hasattr(ctypes, "windll"):
        raise ComputerError("unsupported_platform", "Win32 foreground input is available only on Windows.")
    return ctypes.windll.user32


def _validate_window(user32, hwnd, pid):
    if not hwnd or not user32.IsWindow(hwnd):
        raise ComputerError("stale_window", "The approved Windows target no longer exists; no input was sent.")
    actual_pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(actual_pid))
    if int(actual_pid.value) != int(pid):
        raise ComputerError("target_changed", "The approved HWND now belongs to another process; no input was sent.")


def _activate(user32, hwnd):
    if int(user32.GetForegroundWindow()) == int(hwnd):
        return True
    kernel32 = ctypes.windll.kernel32
    current_thread = kernel32.GetCurrentThreadId()
    foreground = user32.GetForegroundWindow()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    attached_foreground = bool(foreground_thread and foreground_thread != current_thread
                               and user32.AttachThreadInput(current_thread, foreground_thread, True))
    attached_target = bool(target_thread and target_thread != current_thread
                           and user32.AttachThreadInput(current_thread, target_thread, True))
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached_target:
            user32.AttachThreadInput(current_thread, target_thread, False)
        if attached_foreground:
            user32.AttachThreadInput(current_thread, foreground_thread, False)
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if int(user32.GetForegroundWindow()) == int(hwnd):
            return True
        time.sleep(.01)
    return False


def _window_rect(user32, hwnd):
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ComputerError("window_bounds_unavailable", "Windows did not report the approved target bounds.")
    return [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)]


def _window_point(rect, point, image_size):
    width, height = image_size
    if width <= 0 or height <= 0:
        raise ComputerError("invalid_frame", "The approved screenshot has no usable pixel geometry.")
    return (
        rect[0] + point[0] * (rect[2] - rect[0]) / width,
        rect[1] + point[1] * (rect[3] - rect[1]) / height,
    )


def _cursor(user32):
    point = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        raise ComputerError("cursor_unavailable", "Windows did not report the physical cursor position.")
    return [int(point.x), int(point.y)]


def _set_cursor(user32, point):
    if not user32.SetCursorPos(round(point[0]), round(point[1])):
        raise ComputerError(
            "input_desktop_unavailable",
            "The shared Windows pointer is locked by another automation host; no pointer action was sent.",
            details={"input_sent": False},
        )
    actual = _cursor(user32)
    if actual != [round(point[0]), round(point[1])]:
        raise ComputerError("input_failed", "Windows did not move the pointer to the approved target.")
    return actual


def _point_hits_window(user32, hwnd, point):
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    hit = user32.WindowFromPoint(wintypes.POINT(round(point[0]), round(point[1])))
    return bool(hit and (int(hit) == int(hwnd) or user32.IsChild(hwnd, hit)))


def _mouse_event(user32, flags, data=0):
    event = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, data & 0xFFFFFFFF, flags, 0, 0))
    if user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
        raise ComputerError(
            "input_failed", "Windows refused the approved pointer event; do not retry blindly.",
            details={"win32_error": ctypes.get_last_error()},
        )


def _restore(user32, foreground, cursor):
    cursor_restored = bool(user32.SetCursorPos(cursor.x, cursor.y))
    focus_restored = not foreground or _activate(user32, foreground)
    return focus_restored, cursor_restored


def foreground_scroll(*, hwnd, pid, point, image_size, direction, amount, by,
                      previous_foreground=None):
    """Perform one approved wheel gesture and restore focus and pointer."""
    user32 = _user32()
    _validate_window(user32, hwnd, pid)
    prior_foreground = (int(user32.GetForegroundWindow()) if previous_foreground is None
                        else int(previous_foreground))
    prior_cursor = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(prior_cursor)):
        raise ComputerError("cursor_unavailable", "Could not save the physical cursor; no input was sent.")
    if direction not in ("up", "down", "left", "right"):
        raise ComputerError("invalid_direction", "Scroll direction must be up, down, left, or right.")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or not math.isfinite(amount) or amount <= 0:
        raise ComputerError("invalid_amount", "Scroll amount must be a positive finite number.")
    if by not in ("line", "page"):
        raise ComputerError("invalid_scroll_unit", "Scroll unit must be line or page.")
    rect = _window_rect(user32, hwnd)
    screen_point = _window_point(rect, point, image_size)
    foreground_acquired = False
    try:
        foreground_acquired = _activate(user32, hwnd)
        if not _point_hits_window(user32, hwnd, screen_point):
            raise ComputerError("foreground_unavailable", "The approved scroll point is not visibly owned by the target; no input was sent.")
        actual_point = _set_cursor(user32, screen_point)
        delta = round(120 * amount * (3 if by == "page" else 1))
        horizontal = direction in ("left", "right")
        if direction in ("down", "left"):
            delta = -delta
        _mouse_event(user32, MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL, delta)
    finally:
        focus_restored, cursor_restored = _restore(user32, prior_foreground, prior_cursor)
    return {
        "delivery": {"mode": "foreground"}, "route": "win32_sendinput",
        "effect": "unverifiable", "focus_restored": focus_restored,
        "cursor_restored": cursor_restored,
        "foreground_acquired_before_input": foreground_acquired,
        "window_pixel_point": list(point), "screen_point": actual_point,
        "target_rect": rect,
    }


def foreground_drag(*, hwnd, pid, start, end, image_size, duration_ms,
                    previous_foreground=None):
    """Perform one approved physical drag and restore focus and pointer."""
    user32 = _user32()
    _validate_window(user32, hwnd, pid)
    prior_foreground = (int(user32.GetForegroundWindow()) if previous_foreground is None
                        else int(previous_foreground))
    prior_cursor = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(prior_cursor)):
        raise ComputerError("cursor_unavailable", "Could not save the physical cursor; no input was sent.")
    rect = _window_rect(user32, hwnd)
    screen_start = _window_point(rect, start, image_size)
    screen_end = _window_point(rect, end, image_size)
    released = False
    foreground_acquired = False
    try:
        foreground_acquired = _activate(user32, hwnd)
        if (not _point_hits_window(user32, hwnd, screen_start)
                or not _point_hits_window(user32, hwnd, screen_end)):
            raise ComputerError("foreground_unavailable", "The approved drag path is not visibly owned by the target; no input was sent.")
        actual_start = _set_cursor(user32, screen_start)
        _mouse_event(user32, MOUSEEVENTF_LEFTDOWN)
        steps = min(90, max(2, round(max(50, duration_ms) / 16)))
        for step in range(1, steps + 1):
            ratio = step / steps
            _set_cursor(user32, (
                screen_start[0] + (screen_end[0] - screen_start[0]) * ratio,
                screen_start[1] + (screen_end[1] - screen_start[1]) * ratio,
            ))
            time.sleep(max(0, duration_ms) / 1000 / steps)
        _mouse_event(user32, MOUSEEVENTF_LEFTUP)
        actual_end = _cursor(user32)
        released = True
    finally:
        if not released:
            try:
                _mouse_event(user32, MOUSEEVENTF_LEFTUP)
            except Exception:
                pass
        focus_restored, cursor_restored = _restore(user32, prior_foreground, prior_cursor)
    return {
        "delivery": {"mode": "foreground"}, "route": "win32_sendinput",
        "effect": "unverifiable", "focus_restored": focus_restored,
        "cursor_restored": cursor_restored,
        "foreground_acquired_before_input": foreground_acquired,
        "window_pixel_start": list(start), "window_pixel_end": list(end),
        "actual_start": actual_start, "actual_end": actual_end,
        "target_rect": rect,
    }
