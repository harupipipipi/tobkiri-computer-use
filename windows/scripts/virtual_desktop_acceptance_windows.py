"""Move only a disposable fixture to another Windows virtual desktop and test Cua."""
from __future__ import annotations

import argparse
import ctypes
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import time
import uuid
import winreg

from tobkiri_computer_use import Computer, ComputerError


REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops"


def registry_desktops():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH) as key:
        ids, _ = winreg.QueryValueEx(key, "VirtualDesktopIDs")
        current, _ = winreg.QueryValueEx(key, "CurrentVirtualDesktop")
    desktops = [uuid.UUID(bytes_le=ids[index:index + 16])
                for index in range(0, len(ids), 16) if len(ids[index:index + 16]) == 16]
    return desktops, uuid.UUID(bytes_le=current)


def read_json(path, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8-sig"))
        time.sleep(.05)
    raise TimeoutError(f"Fixture did not become ready: {path}")


def read_events(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()]


def wait_event(path, name, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        match = next((row for row in read_events(path) if row.get("event") == name), None)
        if match:
            return match
        time.sleep(.05)
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--driver", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    fixture = root / "artifacts" / "TobkiriWindowsFixture.exe"
    if not fixture.exists():
        subprocess.run([sys.executable, str(root / "scripts" / "build_fixture_windows.py"),
                        "--output", str(fixture)], check=True)

    desktops, current = registry_desktops()
    alternate = next((desktop for desktop in desktops if desktop != current), None)
    report = {
        "platform": "windows",
        "desktops": [str(value) for value in desktops],
        "current_before": str(current),
        "alternate": str(alternate) if alternate else None,
        "checks": {},
    }
    if alternate is None:
        report["passed"] = False
        report["reason"] = "No existing alternate virtual desktop; no desktop was created or switched."
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        raise SystemExit(2)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tobkiri-virtual-desktop-") as temporary:
        temporary = Path(temporary)
        ready = temporary / "ready.json"
        events = temporary / "events.jsonl"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen([
            str(fixture), "--mode", "target", "--ready-file", str(ready),
            "--event-log", str(events), "--desktop-id", str(alternate),
        ], creationflags=flags)
        try:
            fixture_state = read_json(ready)
            report["fixture"] = fixture_state
            report["checks"]["moved_off_current"] = {
                "passed": fixture_state["desktop_hresult"] == 0
                          and not fixture_state["on_current_desktop"]
                          and fixture_state["desktop_id"].casefold() == str(alternate).casefold(),
                "desktop_move_event": wait_event(events, "desktop_move"),
            }
            foreground_before = int(ctypes.windll.user32.GetForegroundWindow())
            with Computer(command=[args.driver, "mcp"], cursor_follow_interval=None) as computer:
                rows = [row for row in computer.windows(pid=fixture_state["pid"])
                        if row.get("window_id") == fixture_state["hwnd"]]
                report["checks"]["cua_lists_off_desktop_window"] = {
                    "passed": len(rows) == 1,
                    "matches": rows,
                }
                if len(rows) != 1:
                    raise ComputerError("window_not_listed", "Cua did not list the off-desktop fixture window.")
                window = computer.window(pid=fixture_state["pid"], window_id=fixture_state["hwnd"])
                observation = window.observe(max_dimension=900, max_elements=1000)
                report["checks"]["off_desktop_capture"] = {
                    "passed": bool(observation.image and observation.frame),
                    "image_size": ([observation.frame.pixel_width, observation.frame.pixel_height]
                                   if observation.frame else None),
                    "elements": len(observation.elements),
                    "labels": [element.label for element in observation.elements[:20]],
                }
                # UIA intentionally returned only a shallow tree on the hidden
                # virtual desktop. Use a current screenshot-bound point in this
                # disposable, fixed-layout fixture to test the pixel route.
                result = window.click(observation.point(
                    observation.frame.pixel_width * 290 / 900,
                    observation.frame.pixel_height * 260 / 771,
                ))
                increment = wait_event(events, "increment")
                report["checks"]["off_desktop_background_click"] = {
                    "passed": bool(increment and foreground_before == int(ctypes.windll.user32.GetForegroundWindow())),
                    "delivery": result.delivery,
                    "event": increment,
                    "foreground_unchanged": foreground_before == int(ctypes.windll.user32.GetForegroundWindow()),
                }
            _, current_after = registry_desktops()
            report["current_after"] = str(current_after)
            report["checks"]["desktop_never_switched"] = {
                "passed": current_after == current,
            }
        except Exception as exc:
            report["error"] = exc.as_dict() if isinstance(exc, ComputerError) else {
                "type": type(exc).__name__, "message": str(exc)}
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        report["events"] = read_events(events)

    required = {
        "moved_off_current", "cua_lists_off_desktop_window", "off_desktop_capture",
        "off_desktop_background_click", "desktop_never_switched",
    }
    report["passed"] = (not report.get("error") and required.issubset(report["checks"])
                        and all(report["checks"][name].get("passed") for name in required))
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
