"""Opt-in native check: operate only our fixture without foreground takeover.

Build TobkiriFocusFixture and artifacts/focus-probe first. Records only the
frontmost pid and focused element role/geometry, never user text or titles.
"""
from pathlib import Path
import json
import subprocess
import threading

from tobkiri_computer_use import Computer, ComputerError
from tobkiri_computer_use.transport import structured

root = Path(__file__).resolve().parents[1]
app = root / "artifacts/TobkiriFocusFixture.app"
probe = root / "artifacts/focus-probe"
samples = []
monitor = subprocess.Popen([str(probe), "55"], stdout=subprocess.PIPE, text=True)
ready = threading.Event()
def read():
    for line in monitor.stdout:
        samples.append(json.loads(line))
        ready.set()
reader = threading.Thread(target=read, daemon=True)
reader.start()
assert ready.wait(5), "Focus probe did not start"
baseline = samples[0]
report = {"baseline": baseline, "operations": []}
try:
    with Computer() as computer:
        launch = structured(computer.tool("launch_app", {"bundle_id": "local.tobkiri.tobkirifocusfixture", "additional_arguments": ["--single"]}))
        pid = launch["pid"]
        report["fixture_pid"] = pid
        try:
            rows = computer.windows(pid=pid, title="Tobkiri Fixture A")
            assert len(rows) == 1, rows
            w = computer.window(pid=pid, window_id=rows[0]["window_id"], name="focus-test")
            state = w.observe()
            report["keyboard_route"] = state.to_dict()["input"]
            for name, action in [
                ("set_value", lambda: w.set_value("Name", "Background value")),
                ("type_text", lambda: w.type_text("Name", " + typed")),
                ("press_key", lambda: w.press_key("a", target=w.observe().find("Name"))),
                ("click", lambda: w.click("Apply")),
            ]:
                start = len(samples)
                try:
                    result = action()
                    report["operations"].append({"action": name, "delivery": result.delivery,
                                                 "fixture_value": result.observation.find("Name").value,
                                                 "focus_unchanged": all(s == baseline for s in samples[start:])})
                except ComputerError as exc:
                    report["operations"].append({"action": name, "error": exc.as_dict(),
                                                 "focus_unchanged": all(s == baseline for s in samples[start:])})
            w.observe().save(root / "artifacts/background-focus-result.png")
        finally:
            # Same transport owns the launched fixture. Never kill a user app.
            computer.tool("kill_app", {"pid": pid})
finally:
    monitor.terminate()
    monitor.wait(timeout=3)
    reader.join(timeout=3)
    monitor.stdout.close()
    report["samples"] = len(samples)
    report["frontmost_pid_unchanged"] = all(s["pid"] == baseline["pid"] for s in samples)
    report["focused_element_probe_available"] = all(s.get("focused_element_status") == 0 for s in samples)
    report["focused_element_role_geometry_unchanged"] = all(s == baseline for s in samples) if report["focused_element_probe_available"] else None
    report["foreground_takeover_tested"] = False
    (root / "artifacts/background-focus.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False, indent=2))
