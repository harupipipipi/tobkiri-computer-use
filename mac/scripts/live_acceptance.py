"""Opt-in acceptance on the two dedicated TobkiriFixture windows only."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import statistics
import time

from tobkiri_computer_use import ClickStep, Computer, ComputerError
from tobkiri_computer_use.runtime import driver_command

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--driver", help="Explicit native candidate executable; requires --socket")
parser.add_argument("--socket", help="Already running candidate's socket; requires --driver")
parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts")
parser.add_argument("--measure-latency", action="store_true",
                    help="Compare normal/fast virtual motion and clicks on the dedicated fixture")
parser.add_argument("--fast-demo", action="store_true",
                    help="Show only fast teleport moves and counter clicks on both fixture windows")
parser.add_argument("--wait-demo-start", action="store_true",
                    help="Pause the fast demo after saving initial observations; Enter starts it")
args = parser.parse_args()
if bool(args.driver) != bool(args.socket):
    parser.error("Supply --driver and --socket together; candidate tests never change trusted setup")
if args.fast_demo and args.measure_latency:
    parser.error("Choose --fast-demo or --measure-latency")
if args.wait_demo_start and not args.fast_demo:
    parser.error("--wait-demo-start requires --fast-demo")
OUT = args.output_dir.resolve()
if not OUT.is_relative_to((ROOT / "artifacts").resolve()):
    parser.error("Save live artifacts under this checkout's mac/artifacts directory")
OUT.mkdir(parents=True, exist_ok=True)
command = driver_command(driver=args.driver, endpoint=args.socket) if args.socket else None


def count(state):
    return int(re.search(r"Count: (\d+)", state.tree).group(1))


report = {"checks": {}, "timings_seconds": {}}
with Computer(command=command) as computer:
    report["driver"] = computer.transport.server_info
    if args.driver:
        report["driver_binary_sha256"] = hashlib.sha256(Path(args.driver).read_bytes()).hexdigest()
    a = computer.window(app="TobkiriFixture", title="Tobkiri Fixture A", name="tobkiri-left")
    b = computer.window(app="TobkiriFixture", title="Tobkiri Fixture B", name="tobkiri-right")
    report["targets"] = [a.target, b.target]
    if args.fast_demo:
        for window in (a, b):
            window.set_cursor_speed("fast")
        states = [a.observe(), b.observe()]
        for label, state in zip(("left", "right"), states):
            state.save(OUT / f"demo-{label}-before.png", marks=False)
            (OUT / f"demo-{label}-before.json").write_text(
                json.dumps(state.raw, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"demo_elements": [[{"label": element.label, "role": element.role}
                                             for element in state.elements] for state in states]},
                         ensure_ascii=False), flush=True)
        if args.wait_demo_start:
            print("FAST_DEMO_READY", flush=True)
            input()
            # The host may inspect the saved images before starting the demo.
            # Reobserve after that pause rather than retaining startup handles.
            states = [a.observe(), b.observe()]

        # The fixture controls stay in place; these are fresh screenshot-bound
        # centers from their AX elements, not hard-coded desktop coordinates.
        paths = [[state.find(label).point for label in ("Name", "Increment", "Apply")]
                 for state in states]
        start = time.perf_counter()
        move_count = 0
        for repeat in range(6):
            for index in range(3):
                for window, state, path in zip((a, b), states, paths):
                    point = path[(index + repeat) % len(path)]
                    window.move(state.point(point.x, point.y))
                    move_count += 1
        report["demo"] = {"profile": "fast", "move_count": move_count,
                          "moves_seconds": time.perf_counter() - start}

        # Zero spacing requests the next click as soon as the previous one
        # completes. Native checks stay enabled and elapsed time is reported.
        points = [state.find("Increment").point for state in states]
        initial_counts = [count(state) for state in states]
        start = time.perf_counter()
        sequences = computer.parallel(
            lambda: a.timeline([ClickStep(0, points[0]) for _ in range(12)], on_late="stretch"),
            lambda: b.timeline([ClickStep(0, points[1]) for _ in range(12)], on_late="stretch"),
        )
        report["demo"]["clicks_seconds"] = time.perf_counter() - start
        for label, sequence, initial in zip(("left", "right"), sequences, initial_counts):
            if isinstance(sequence, Exception):
                raise sequence
            assert sequence.status == "completed", sequence.to_dict()
            assert count(sequence.observation) == initial + 12
            sequence.observation.save(OUT / f"demo-{label}-after.png", marks=False)
            report["demo"][label] = {"before": initial,
                                      "after": count(sequence.observation),
                                      "timeline": {key: value for key, value in sequence.to_dict().items()
                                                   if key != "observation"}}
        report["checks"]["fast_demo_both_counters_incremented_twelve_times"] = True
        (OUT / "demo.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"checks": report["checks"], "moves": move_count,
                          "moves_seconds": round(report["demo"]["moves_seconds"], 3),
                          "clicks": 24, "clicks_seconds": round(report["demo"]["clicks_seconds"], 3),
                          "final_counts": [count(s.observation) for s in sequences]},
                         ensure_ascii=False), flush=True)
        raise SystemExit(0)
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

    if args.measure_latency:
        report["latency"] = {}
        for profile in ("normal", "fast"):
            a.set_cursor_speed(profile)
            state = a.observe()
            center = state.find("Increment").point
            points = [(center.x - 25, center.y), (center.x + 25, center.y)]
            moves, clicks = [], []
            for i in range(6):
                started = time.perf_counter()
                a.move(state.point(*points[i % 2]))
                moves.append(time.perf_counter() - started)
            initial_count = count(state)
            for i in range(6):
                started = time.perf_counter()
                action = a.click(state.point(*points[i % 2]))
                clicks.append(time.perf_counter() - started)
                state = action.observation
            assert count(state) == initial_count + 6
            report["latency"][profile] = {
                "move_seconds": moves, "move_median_seconds": statistics.median(moves),
                "click_with_observation_seconds": clicks,
                "click_median_seconds": statistics.median(clicks),
            }
        state = a.observe()
        initial_count = count(state)
        point = state.find("Increment").point
        sequence = a.timeline([ClickStep(i * .025, point) for i in range(12)], on_late="stretch")
        report["latency"]["timeline"] = {
            key: value for key, value in sequence.to_dict().items() if key != "observation"
        }
        assert sequence.status == "completed", sequence.to_dict()
        assert count(sequence.observation) == initial_count + 12
        report["checks"]["latency_normal_fast_and_timeline_counts_match"] = True
        report["latency"]["scope"] = "Dedicated fixture; host RPC timing, not measured OS event or audio onset"
        sequence.observation.save(OUT / "latency-final.png", marks=False)

(OUT / "acceptance.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(report,ensure_ascii=False,indent=2))
