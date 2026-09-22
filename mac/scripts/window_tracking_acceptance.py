"""Opt-in native regression: move only newly launched disposable fixture windows."""
from pathlib import Path
import json
import math
import re
import subprocess
import time

from tobkiri_computer_use import Computer, ComputerError
from tobkiri_computer_use.transport import structured

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts"
APP = OUT / "TobkiriTrackingFixture.app"


def count(state):
    return int(re.search(r"Count: (\d+)", state.tree).group(1))


def wait_cursor(computer, w, expected=None, phase="following"):
    start = time.monotonic()
    while time.monotonic() - start < 5:
        status = computer._cursors.status(w)
        point = status.get("screen_point")
        if status["phase"] == phase and (expected is None or point and math.dist(point, expected) < .5):
            native = structured(w._call("get_agent_cursor_state"))
            if expected is None or math.dist([native["position"]["x"], native["position"]["y"]], expected) < 2:
                return {"status": status, "native": native, "readback_seconds": round(time.monotonic()-start, 3)}
        time.sleep(.025)
    raise AssertionError(f"Cursor did not follow: {status}; expected {expected}")


def move_external(computer, w, bounds):
    # Simulates a user's window move without invalidating helper observations.
    result = structured(computer.transport.call("set_window_frame", {
        "pid": w.surface[0], "window_id": w.surface[1], "session": w.session, **bounds}))
    assert result["effect"] == "confirmed", result


def main():
    assert APP.is_dir(), "Build with scripts/build_fixture.py --name TobkiriTrackingFixture"
    subprocess.run(["/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister", "-f", str(APP)], check=True)
    report = {"checks": {}, "positions": [], "visual_pixels_verified": False}
    try:
        with Computer() as c:
            report["driver"] = c.transport.server_info
            launched = structured(c.tool("launch_app", {"bundle_id": "local.tobkiri.tobkiritrackingfixture", "creates_new_application_instance": True}))
            pid = launched["pid"]
            report["fixture_pid"] = pid
            try:
                a = c.window(pid=pid, title="Tobkiri Fixture A", name="tracking-A")
                b = c.window(pid=pid, title="Tobkiri Fixture B", name="tracking-B")
                original = a.observe(max_dimension=600)
                old = original.find("Increment").point
                zoom = original.zoom([old.x-40, old.y-20, old.x+40, old.y+20], scale=3)
                zoom_point = zoom.point(120, 60)
                other = b.observe(max_dimension=600)
                other_count = count(other)
                a.move(old); b.move(other.find("Increment"))
                initial = original.raw["window_bounds"]
                local = [old.x*original.frame.width/original.frame.pixel_width,
                         old.y*original.frame.height/original.frame.pixel_height]
                for dx, dy in [(0, 95), (20, -50), (0, 40)]:
                    bounds = {**initial, "x": initial["x"]+dx, "y": initial["y"]+dy}
                    move_external(c, a, bounds)
                    report["positions"].append(wait_cursor(c, a, [bounds["x"]+local[0], bounds["y"]+local[1]]))
                    assert c._latest[a.surface] == original.id
                    assert a._last is original  # Idle polling never captures or changes observations.
                report["checks"]["idle_cursor_follows_three_moves"] = True
                # This coordinate was computed before all three window moves.
                result = a.click(zoom_point)
                assert count(result.observation) == count(original)+1
                assert count(b.observe()) == other_count
                assert (original.frame.x, original.frame.y) == (initial["x"], initial["y"])
                report["checks"]["old_zoom_coordinate_clicks_same_button_only"] = True

                semantic = a.observe(max_dimension=600)
                bounds["y"] -= 35
                move_external(c, a, bounds)
                result = a.click(semantic.find("Increment"))
                assert count(result.observation) == count(semantic)+1
                report["checks"]["old_element_refreshes_after_move"] = True
                a.move(result.observation.find("Increment"))
                wait_cursor(c, a, [bounds["x"]+local[0], bounds["y"]+local[1]])
                result.observation.save(OUT / "window-tracking-result.png")

                # Exercise the standard Cua MCP path too, using its own session.
                raw_window = c.window(pid=pid, window_id=a.surface[1], name="tracking-raw")
                raw_args = {"pid": pid, "window_id": a.surface[1], "session": raw_window.session,
                            "include_screenshot": True, "max_dimension": 600}
                raw = structured(c.tool("get_window_state", raw_args))
                old_count = count(a.observe(max_dimension=600))
                bounds["y"] += 20
                move_external(c, a, bounds)
                c.tool("click", {"target": a.target, "x": old.x, "y": old.y, "session": raw_window.session})
                assert count(a.observe()) == old_count+1
                raw = structured(c.tool("get_window_state", raw_args))
                token = next(e["element_token"] for e in raw["elements"] if e.get("label") == "Increment")
                bounds["y"] -= 20
                move_external(c, a, bounds)
                c.tool("click", {"pid": pid, "window_id": a.surface[1], "element_token": token,
                                 "session": raw_window.session})
                assert count(a.observe()) == old_count+2
                assert count(b.observe()) == other_count
                report["checks"]["raw_cua_pixel_and_token_translation"] = True
                c.tool("end_session", {"session": raw_window.session})
                c._sessions.discard(raw_window.session)

                # Size changes still invalidate old image coordinates.
                saved = a.observe()
                move_external(c, a, {**bounds, "width": bounds["width"]+10})
                state = wait_cursor(c, a, phase="geometry_changed")
                assert state["native"]["enabled"] is False
                try:
                    a.click(saved.find("Increment").point)
                    raise AssertionError("Resized-window coordinate was accepted")
                except ComputerError as exc:
                    assert exc.code in ("stale_geometry", "stale_observation"), exc.as_dict()
                report["checks"]["resize_hides_cursor_and_refuses_old_point"] = True
                fresh = a.observe()
                a.move(fresh.find("Increment"))
                assert c.cursor_status(pid=pid, window_id=a.surface[1])[0]["phase"] == "following"
                report["checks"]["fresh_observation_restores_cursor"] = True
                report["other_cursor"] = c.cursor_status(pid=pid, window_id=b.surface[1])
                report["checks"]["second_cursor_remains_bound_to_its_window"] = c._cursors.status(b)["phase"] == "following"
            finally:
                # This process was newly launched above and contains only fixture data.
                c.tool("kill_app", {"pid": pid})
    finally:
        (OUT / "window-tracking.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
