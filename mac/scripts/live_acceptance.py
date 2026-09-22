"""Opt-in acceptance on the two dedicated TobkiriFixture windows only."""
from pathlib import Path
import json
import re
import time

from tobkiri_computer_use import Computer, ComputerError

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts"
OUT.mkdir(exist_ok=True)


def count(state):
    return int(re.search(r"Count: (\d+)", state.tree).group(1))


report = {"checks": {}, "timings_seconds": {}}
with Computer() as computer:
    report["driver"] = computer.transport.server_info
    a = computer.window(app="TobkiriFixture", title="Tobkiri Fixture A", name="tobkiri-left")
    b = computer.window(app="TobkiriFixture", title="Tobkiri Fixture B", name="tobkiri-right")
    report["targets"] = [a.target, b.target]
    before = a.observe()
    n = count(before)
    start = time.monotonic()
    r = a.click(before.find("Increment"))
    assert count(r.observation) == n+1
    text = "Tobkiri Python ✓"
    r = a.set_value("Name", text, expect=[{"element": {
        "selector": {"label_contains": "Name", "role": "AXTextField"}, "value_equals": text}}])
    report["native_verification"] = r.verification
    assert r.observation.find("Name").value == text
    r = a.click("Apply")
    assert "Saved: " + text in r.observation.tree
    report["timings_seconds"]["three_actions_with_readback"] = round(time.monotonic()-start, 3)
    report["checks"]["semantic_click_type_apply"] = True
    r.observation.save(OUT / "native-result.png")
    r.observation.save(OUT / "native-elements.png", labels=True)
    try:
        a.click(before.find("Increment"))
        raise AssertionError("Old element was accepted")
    except ComputerError as exc:
        assert exc.code == "stale_observation"
    report["checks"]["stale_element_refused"] = True

    # Two crops from one source do not overwrite each other's mapping.
    s = a.observe(max_dimension=600)
    button = s.find("Increment").point
    z = s.zoom([button.x-60, button.y-30, button.x+60, button.y+30], scale=4)
    unused_other_crop = s.zoom([0,0,70,70])
    z.save(OUT / "native-zoom.png")
    zx = (button.x-z.crop.left)*z.crop.output_width/z.crop.width
    zy = (button.y-z.crop.top)*z.crop.output_height/z.crop.height
    n = count(s)
    r = a.click(z.point(zx,zy))
    assert count(r.observation) == n+1
    assert r.observation.frame == s.frame
    report["checks"]["zoom_pixel_click_after_second_crop"] = True
    report["checks"]["automatic_observation_keeps_image_scale"] = True
    r.observation.save(OUT / "native-zoom-click.png")

    # Pure translation preserves coordinates and refreshes the driver's frame.
    s = a.observe()
    bounds = s.raw["window_bounds"]
    try:
        computer.transport.call("set_window_frame", {"pid":a.surface[0],"window_id":a.surface[1],
            "x":bounds["x"]+20,"y":bounds["y"],"width":bounds["width"],"height":bounds["height"],"session":a.session})
        result = a.click(s.find("Increment").point)
        assert count(result.observation) == count(s)+1
        report["checks"]["moved_window_preserves_pixel_input"] = True
    finally:
        computer.transport.call("set_window_frame", {"pid":a.surface[0],"window_id":a.surface[1],
            **bounds,"session":a.session})

    sa, sb = a.observe(), b.observe()
    na, nb = count(sa), count(sb)
    start = time.monotonic()
    results = computer.parallel(lambda:a.click("Increment"),lambda:b.click("Increment"))
    for result in results:
        if isinstance(result, Exception): raise result
    assert count(results[0].observation)==na+1 and count(results[1].observation)==nb+1
    assert a.session != b.session
    report["timings_seconds"]["two_window_parallel_jobs"] = round(time.monotonic()-start,3)
    report["checks"]["parallel_two_cursors_two_windows"] = True
    report["sessions"] = [a.session,b.session]

    for w, result, name in zip((a,b),results,("left","right")):
        state=result.observation
        report[f"cursor_{name}"] = w.move(state.find("Increment"))
        assert report[f"cursor_{name}"]["position_matches"]
        state.save(OUT/f"native-{name}.png")
    computer.transport.call("get_desktop_state", {"session":b.session,
        "screenshot_out_file":str(OUT/"native-cursors-desktop.png")})
    report["checks"]["cursor_reported_screen_positions_match"] = True
    report["visual_verification"] = "Inspect native-cursors-desktop.png separately; state alone does not prove painted pixels."

(OUT / "acceptance.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(report,ensure_ascii=False,indent=2))
