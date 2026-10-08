"""Opt-in, disposable Windows acceptance test for background Cua delivery."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from tobkiri_computer_use import Computer, ComputerError, ConsentDecision
from tobkiri_computer_use.runtime import driver_command
from tobkiri_computer_use.transport import structured


def foreground_window():
    return int(ctypes.windll.user32.GetForegroundWindow())


def force_fixture_foreground(hwnd):
    """Put the disposable witness in front so target focus-steal is measurable."""
    user32 = ctypes.windll.user32
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
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached_target:
            user32.AttachThreadInput(current_thread, target_thread, False)
        if attached_foreground:
            user32.AttachThreadInput(current_thread, foreground_thread, False)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if foreground_window() == hwnd:
            return True
        time.sleep(.05)
    return False


def cursor_position():
    point = wintypes.POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError()
    return [point.x, point.y]


def foreground_pointer_available():
    """Probe whether this process can use the shared Windows input desktop."""
    user32 = ctypes.windll.user32
    point = wintypes.POINT()
    clip = wintypes.RECT()
    if not user32.GetCursorPos(ctypes.byref(point)) or not user32.GetClipCursor(ctypes.byref(clip)):
        return False
    next_x = point.x + 1 if point.x + 1 < clip.right else point.x - 1
    moved = bool(user32.SetCursorPos(next_x, point.y))
    observed = wintypes.POINT()
    changed = bool(user32.GetCursorPos(ctypes.byref(observed))
                   and (observed.x, observed.y) == (next_x, point.y))
    restored = bool(user32.SetCursorPos(point.x, point.y)) if moved else True
    return moved and changed and restored


def wait_file(path, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8-sig"))
        time.sleep(.05)
    raise TimeoutError(f"Fixture did not become ready: {path}")


def wait_window(computer, pid, title_prefix, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        matches = [row for row in computer.windows(pid=pid)
                   if row.get("title", "").startswith(title_prefix)]
        if len(matches) == 1:
            return matches[0]
        time.sleep(.1)
    raise TimeoutError(f"Expected one {title_prefix!r} window for pid {pid}")


def read_events(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()]


def wait_event(path, event, predicate=lambda row: True, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        match = next((row for row in read_events(path)
                      if row.get("event") == event and predicate(row)), None)
        if match:
            return match
        time.sleep(.05)
    return None


def first_label(observation, text):
    matches = observation.find_all(text)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one element {text!r}, got {len(matches)}")
    return matches[0]


def visible_rows(observation):
    return [element.label for element in observation.elements
            if element.role == "ListItem" and element.point is not None]


def drag_points(observation):
    """Choose two points inside the UIA-reported disposable drag surface."""
    panel = observation.find("Drag canvas")
    rect = panel.raw["frame"]
    start = observation.frame.from_screen(rect["x"] + rect["w"] * .15,
                                          rect["y"] + rect["h"] * .7)
    end = observation.frame.from_screen(rect["x"] + rect["w"] * .75,
                                        rect["y"] + rect["h"] * .7)
    return observation.point(*start), observation.point(*end)


def allow_acceptance_foreground(request):
    return ConsentDecision(request.id, request.digest, True)


def visible_demo(args, fixture):
    """User-requested visible replay; background inputs and a persistent fixture."""
    directory = Path(tempfile.mkdtemp(prefix="visible-demo-", dir=args.output.parent))
    ready, events = directory / "ready.json", directory / "events.jsonl"
    process = subprocess.Popen([
        str(fixture), "--mode", "target", "--ready-file", str(ready),
        "--event-log", str(events),
    ], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    report = {"mode": "visible-demo", "steps": [], "passed": False,
              "physical_input_requested": False, "artifact_directory": str(directory)}
    try:
        target = wait_file(ready)
        with Computer(command=driver_command(driver=args.driver), companion=True,
                      approval_callback=None) as computer:
            row = wait_window(computer, target["pid"], "Tobkiri Windows Target")
            window = computer.window(pid=row["pid"], window_id=row["window_id"])
            # The visible-demo flag requests presentation of this exact disposable
            # fixture. It does not approve any foreground/hardware input action.
            if not force_fixture_foreground(row["window_id"]):
                raise RuntimeError("The disposable fixture could not be shown in front.")
            report.update(pid=row["pid"], window_id=row["window_id"], title=row["title"])
            state = window.observe()
            state.save(args.output.with_name(args.output.stem + "-before.png"))
            report["observed_elements"] = [element.to_dict() for element in state.elements[:8]]
            args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"VISIBLE {row['title']} - starting in 15 seconds", flush=True)
            time.sleep(15)

            def record(label, result, confirmed):
                if not confirmed:
                    raise RuntimeError(f"{label}: fresh fixture state did not confirm the effect; no retry.")
                report["steps"].append({"action": label, "confirmed": True,
                                        "delivery": result.delivery})
                print(f"CONFIRMED {label}", flush=True)
                time.sleep(args.step_delay)

            state = window.observe()
            clicked = window.click(first_label(state, "Increment"))
            record("Increment: Count 1", clicked,
                   wait_event(events, "increment", lambda event: event.get("count") == 1) is not None)

            state = window.observe()
            typed = window.type_text(first_label(state, "Name"), "Hello from Tobkiri")
            name = first_label(typed.observation, "Name")
            record("Name: Hello from Tobkiri", typed, name.value == "Hello from Tobkiri")

            state = window.observe()
            applied = window.click(first_label(state, "Apply"))
            record("Apply: Hello from Tobkiri", applied,
                   wait_event(events, "apply", lambda event: event.get("value") == "Hello from Tobkiri") is not None)

            state = window.observe()
            before_rows = visible_rows(state)
            scrolled = window.scroll(first_label(state, "Scrollable list"), "down", amount=3)
            after_rows = visible_rows(scrolled.observation)
            record("UIA scroll", scrolled, before_rows != after_rows)
            report["visible_rows"] = after_rows
            report["companion"] = computer.companion_status()
            window.observe().save(args.output.with_name(args.output.stem + "-after.png"))
            report["passed"] = True
    except BaseException as error:
        report["error"] = error.as_dict() if isinstance(error, ComputerError) else str(error)
        raise
    finally:
        report["events"] = read_events(events)
        report["window_kept_open"] = args.keep_open and process.poll() is None
        if not args.keep_open and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--driver", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-foreground", action="store_true",
                        help="Approve the test fixture's one-action foreground scroll/drag fallbacks")
    parser.add_argument("--visible-demo", action="store_true",
                        help="Show only the disposable target and replay background input slowly")
    parser.add_argument("--keep-open", action="store_true",
                        help="Leave the visible-demo fixture open for the user to inspect and close")
    parser.add_argument("--step-delay", type=float, default=4,
                        help="Visible-demo pause after each confirmed action (0..30 seconds)")
    args = parser.parse_args()
    if args.keep_open and not args.visible_demo:
        parser.error("--keep-open requires --visible-demo")
    if not 0 <= args.step_delay <= 30:
        parser.error("--step-delay must be between 0 and 30 seconds")
    root = Path(__file__).resolve().parents[1]
    fixture = root / "artifacts" / "TobkiriWindowsFixture.exe"
    if not fixture.exists():
        subprocess.run([sys.executable, str(root / "scripts" / "build_fixture_windows.py"),
                        "--output", str(fixture)], check=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.visible_demo:
        if args.allow_foreground:
            parser.error("--visible-demo uses background input only; omit --allow-foreground")
        visible_demo(args, fixture)
        return
    report = {
        "platform": "windows", "driver": args.driver,
        "environment": {"foreground_pointer_available": None},
        "checks": {},
    }

    with tempfile.TemporaryDirectory(prefix="tobkiri-windows-") as temporary:
        temporary = Path(temporary)
        target_ready = temporary / "target-ready.json"
        witness_ready = temporary / "witness-ready.json"
        target_log = temporary / "target-events.jsonl"
        witness_log = temporary / "witness-events.jsonl"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        target_process = subprocess.Popen([
            str(fixture), "--mode", "target",
            "--ready-file", str(target_ready), "--event-log", str(target_log),
        ], creationflags=flags)
        witness_process = None
        try:
            target = wait_file(target_ready)
            witness_process = subprocess.Popen([
                str(fixture), "--mode", "witness",
                "--ready-file", str(witness_ready), "--event-log", str(witness_log),
            ], creationflags=flags)
            witness = wait_file(witness_ready)
            time.sleep(.8)
            command = [args.driver, "mcp"]
            with Computer(command=command, cursor_follow_interval=None,
                          approval_callback=(allow_acceptance_foreground
                                             if args.allow_foreground else None)) as computer:
                target_row = wait_window(computer, target["pid"], "Tobkiri Windows Target")
                witness_row = wait_window(computer, witness["pid"], "Tobkiri Windows Witness")
                window = computer.window(pid=target_row["pid"], window_id=target_row["window_id"])
                force_fixture_foreground(witness_row["window_id"])
                # Probing moves the physical pointer. A background-only run
                # must not perform that hardware action during test setup.
                pointer_available = (foreground_pointer_available()
                                     if args.allow_foreground else None)
                report["environment"]["foreground_pointer_available"] = pointer_available
                before_foreground = foreground_window()
                before_cursor = cursor_position()
                state = window.observe(max_dimension=900, max_elements=1000)
                state.save(args.output.with_name(args.output.stem + "-before.png"))
                report["observed_elements"] = [element.to_dict() for element in state.elements[:8]]
                report["checks"]["occluded_capture"] = {
                    "passed": bool(state.image and state.frame
                                   and before_foreground != target_row["window_id"]),
                    "image_size": [state.frame.pixel_width, state.frame.pixel_height] if state.frame else None,
                    "elements": len(state.elements),
                    "target_is_background": before_foreground != target_row["window_id"],
                    "witness_is_foreground": before_foreground == witness_row["window_id"],
                }
                increment = first_label(state, "Increment")
                clicked = window.click(increment)
                increment_event = wait_event(target_log, "increment", lambda row: row.get("count") == 1)
                after_foreground = foreground_window()
                after_cursor = cursor_position()
                report["checks"]["background_semantic_click"] = {
                    "passed": (increment_event is not None
                               and before_foreground == after_foreground
                               and before_cursor == after_cursor),
                    "delivery": clicked.delivery,
                    "foreground_before": before_foreground,
                    "foreground_after": after_foreground,
                    "physical_cursor_before": before_cursor,
                    "physical_cursor_after": after_cursor,
                }
                name = first_label(clicked.observation, "Name")
                replaced = window.set_value(name, "Tobkiri Windows")
                apply_button = first_label(replaced.observation, "Apply")
                applied = window.click(apply_button)
                apply_event = wait_event(target_log, "apply",
                                         lambda row: row.get("value") == "Tobkiri Windows")
                report["checks"]["background_value"] = {
                    "passed": (apply_event is not None
                               and foreground_window() == before_foreground
                               and cursor_position() == before_cursor),
                    "set_value_delivery": replaced.delivery,
                    "apply_delivery": applied.delivery,
                }
                pixel_state = applied.observation
                pixel_increment = first_label(pixel_state, "Increment")
                if pixel_increment.point is None:
                    raise RuntimeError("Increment has no screenshot-bound center")
                pixel_before_foreground = foreground_window()
                pixel_before_cursor = cursor_position()
                pixel_clicked = window.click(pixel_state.point(
                    pixel_increment.point.x, pixel_increment.point.y))
                pixel_event = wait_event(target_log, "increment", lambda row: row.get("count") == 2)
                report["checks"]["background_pixel_click"] = {
                    "passed": (pixel_event is not None
                               and foreground_window() == pixel_before_foreground
                               and cursor_position() == pixel_before_cursor),
                    "delivery": pixel_clicked.delivery,
                }
                typed_state = pixel_clicked.observation
                cleared = window.set_value(first_label(typed_state, "Name"), "")
                typed = window.type_text(first_label(cleared.observation, "Name"), "Typed in background")
                typed_apply = window.click(first_label(typed.observation, "Apply"))
                typed_event = wait_event(target_log, "apply",
                                         lambda row: row.get("value") == "Typed in background")
                report["checks"]["background_type_text"] = {
                    "passed": (typed_event is not None
                               and foreground_window() == before_foreground
                               and cursor_position() == before_cursor),
                    "delivery": typed.delivery,
                    "apply_delivery": typed_apply.delivery,
                }
                scroll_state = typed_apply.observation
                scroll_element = first_label(scroll_state, "Scrollable list")
                if scroll_element.point is None:
                    raise RuntimeError("Scrollable list has no screenshot-bound center")
                rows_before_scroll = visible_rows(scroll_state)
                scrolled = window.scroll(scroll_element, "down", amount=3)
                rows_after_scroll = visible_rows(scrolled.observation)
                report["checks"]["background_scroll"] = {
                    "passed": (rows_before_scroll != rows_after_scroll
                               and foreground_window() == before_foreground
                               and cursor_position() == before_cursor),
                    "delivery": scrolled.delivery,
                    "visible_rows_before": rows_before_scroll,
                    "visible_rows_after": rows_after_scroll,
                }
                pixel_scroll_state = scrolled.observation
                pixel_scroll_element = first_label(pixel_scroll_state, "Scrollable list")
                pixel_scroll_point = pixel_scroll_state.point(
                    pixel_scroll_element.point.x, pixel_scroll_element.point.y)
                try:
                    pixel_scrolled = window.scroll(pixel_scroll_point, "down", amount=3)
                    pixel_scroll_error = None
                except ComputerError as exc:
                    pixel_scrolled, pixel_scroll_error = None, exc
                report["checks"]["background_pixel_scroll"] = {
                    "passed": (pixel_scrolled is not None or pixel_scroll_error is not None)
                              and foreground_window() == before_foreground,
                    "delivery": pixel_scrolled.delivery if pixel_scrolled else None,
                    "refusal": pixel_scroll_error.as_dict() if pixel_scroll_error else None,
                    "no_auto_escalation": pixel_scrolled is None,
                }
                if pixel_scrolled is None and args.allow_foreground and pointer_available:
                    foreground_scroll_state = window.observe()
                    foreground_scroll_element = first_label(foreground_scroll_state, "Scrollable list")
                    foreground_rows_before = visible_rows(foreground_scroll_state)
                    foreground_scroll = window.scroll(
                        foreground_scroll_state.point(foreground_scroll_element.point.x,
                                                      foreground_scroll_element.point.y),
                        "down", amount=3, delivery_mode="foreground",
                        fallback_reason="The WindowsForms mouse_scroll background route explicitly refused delivery")
                    scroll_event = wait_event(target_log, "scroll", timeout=.5)
                    foreground_rows_after = visible_rows(foreground_scroll.observation)
                    foreground_scroll_effect = (scroll_event is not None
                                                or foreground_rows_before != foreground_rows_after)
                    foreground_scroll_mode = (foreground_scroll.delivery.get("delivery") or {}).get("mode")
                    report["checks"]["foreground_scroll_fallback"] = {
                        "passed": (foreground_scroll_mode == "foreground"
                                   and foreground_scroll_effect
                                   and foreground_window() == before_foreground),
                        "delivery": foreground_scroll.delivery,
                        "focus_restored": foreground_window() == before_foreground,
                        "effect_observed": foreground_scroll_effect,
                        "visible_rows_before": foreground_rows_before,
                        "visible_rows_after": foreground_rows_after,
                    }
                    drag_state = foreground_scroll.observation
                else:
                    report["checks"]["foreground_scroll_fallback"] = {
                        "passed": True,
                        "skipped": pixel_scrolled is None,
                        "reason": ("shared Windows pointer is locked by another automation host"
                                   if args.allow_foreground and not pointer_available else None),
                    }
                    drag_state = pixel_scrolled.observation if pixel_scrolled else window.observe()
                start, end = drag_points(drag_state)
                try:
                    dragged = window.drag(start, end)
                    drag_error = None
                except ComputerError as exc:
                    dragged, drag_error = None, exc
                drag_event = wait_event(target_log, "drag_end", timeout=.4)
                report["checks"]["background_drag"] = {
                    "passed": ((drag_event is not None if dragged else drag_error is not None)
                               and foreground_window() == before_foreground
                               and cursor_position() == before_cursor),
                    "delivery": dragged.delivery if dragged else None,
                    "refusal": drag_error.as_dict() if drag_error else None,
                    "no_auto_escalation": dragged is None,
                }
                if dragged is None and args.allow_foreground and pointer_available:
                    foreground_drag_state = window.observe()
                    foreground_start, foreground_end = drag_points(foreground_drag_state)
                    foreground_drag = window.drag(
                        foreground_start, foreground_end, delivery_mode="foreground",
                        fallback_reason="The WindowsForms background drag route explicitly refused delivery")
                    drag_event = wait_event(target_log, "drag_end")
                    report["checks"]["foreground_drag_fallback"] = {
                        "passed": drag_event is not None and foreground_window() == before_foreground,
                        "delivery": foreground_drag.delivery,
                        "focus_restored": foreground_window() == before_foreground,
                    }
                else:
                    report["checks"]["foreground_drag_fallback"] = {
                        "passed": True,
                        "skipped": dragged is None,
                        "reason": ("shared Windows pointer is locked by another automation host"
                                   if args.allow_foreground and not pointer_available else None),
                    }
                stale = window.observe()
                fresh = window.observe()
                fresh.save(args.output.with_name(args.output.stem + "-after.png"))
                try:
                    window.click(stale.find("Increment"))
                    stale_result = {"passed": False, "error": None}
                except ComputerError as exc:
                    stale_result = {"passed": exc.code == "stale_observation", "error": exc.as_dict()}
                report["checks"]["stale_observation"] = stale_result
                report["checks"]["fresh_snapshot_changed"] = {
                    "passed": stale.driver_snapshot_id != fresh.driver_snapshot_id,
                    "before": stale.driver_snapshot_id,
                    "after": fresh.driver_snapshot_id,
                }
                report["driver"] = computer.transport.server_info
            report["events"] = read_events(target_log)
        finally:
            for process in (witness_process, target_process):
                if process is not None and process.poll() is None:
                    process.terminate()
            for process in (witness_process, target_process):
                if process is not None:
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)

    report["passed"] = all(check.get("passed") is True for check in report["checks"].values())
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
