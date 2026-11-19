"""Opt-in acceptance on dedicated TobkiriFixture windows only."""
from collections import defaultdict
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
import argparse
import hashlib
import json
import re
import statistics
import subprocess
import threading
import time

from PIL import Image
from tobkiri_computer_use import ClickStep, Computer, ComputerError
from tobkiri_computer_use.runtime import driver_command

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--driver", help="Explicit native candidate executable; requires --socket")
parser.add_argument("--socket", help="Already running candidate's socket; requires --driver")
parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts")
mode = parser.add_mutually_exclusive_group()
mode.add_argument("--measure-latency", action="store_true",
                  help="Compare normal/fast virtual motion and clicks on the dedicated fixture")
mode.add_argument("--fast-demo", action="store_true",
                  help="Show only fast teleport moves and counter clicks on both fixture windows")
mode.add_argument("--profile-timeline", action="store_true",
                  help="Launch disposable control and canvas fixtures and profile 1ms-spaced clicks")
mode.add_argument("--probe-file-sheet", action="store_true",
                  help="Inspect a native Open sheet owned by a disposable TobkiriFixture")
mode.add_argument("--measure-readback", action="store_true",
                  help="Measure semantic edits with image or AX-only readback in a disposable fixture")
mode.add_argument("--check-multiwindow", action="store_true",
                  help="Check exact routing between two overlapping disposable TobkiriFixture windows")
mode.add_argument("--check-electron-multiwindow", action="store_true",
                  help="Run the same exact-window check on a disposable Electron pair")
parser.add_argument("--wait-demo-start", action="store_true",
                    help="Pause the fast demo after saving initial observations; Enter starts it")
args = parser.parse_args()
if bool(args.driver) != bool(args.socket):
    parser.error("Supply --driver and --socket together; candidate tests never change trusted setup")
if args.wait_demo_start and not args.fast_demo:
    parser.error("--wait-demo-start requires --fast-demo")
OUT = args.output_dir.resolve()
if not OUT.is_relative_to((ROOT / "artifacts").resolve()):
    parser.error("Save live artifacts under this checkout's mac/artifacts directory")
OUT.mkdir(parents=True, exist_ok=True)
command = driver_command(driver=args.driver, endpoint=args.socket) if args.socket else None


def count(state):
    return int(re.search(r"Count: (\d+)", state.tree).group(1))


@contextmanager
def launched_fixture(computer, title, *arguments, executable=None):
    binary = executable or ROOT / "artifacts/TobkiriFixture.app/Contents/MacOS/TobkiriFixture"
    with subprocess.Popen([str(binary), *arguments], stdout=subprocess.DEVNULL) as fixture:
        try:
            deadline = time.monotonic() + 8
            rows = []
            while time.monotonic() < deadline and fixture.poll() is None:
                rows = computer.windows(pid=fixture.pid)
                for row in rows:
                    if (row.get("title") == title and row.get("is_on_screen")
                            and row.get("on_current_space") is not False):
                        yield computer.window(pid=fixture.pid, window_id=row["window_id"])
                        return
                time.sleep(.1)
            observed = [(row.get("title"), row.get("is_on_screen"), row.get("on_current_space")) for row in rows]
            raise RuntimeError(f"Dedicated fixture did not show {title}: {observed}, exit={fixture.poll()}")
        finally:
            if fixture.poll() is None:
                fixture.terminate()
                try:
                    fixture.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    fixture.kill()


def profile_sequence(window, state, points, samples):
    phases = defaultdict(list)
    thread = threading.get_ident()
    transport = window.computer.transport
    original = transport.call

    def call(name, arguments=None):
        started = time.perf_counter_ns()
        try:
            return original(name, arguments)
        finally:
            if threading.get_ident() == thread:
                phases[name].append((time.perf_counter_ns() - started) / 1e6)

    steps = [ClickStep(index * .001, state.point(*points[index % len(points)]))
             for index in range(samples)]
    transport.call = call
    try:
        sequence = window.timeline(steps, on_late="stretch", max_lateness=0)
    finally:
        transport.call = original
    events = sequence.events
    gaps = [(right["started"] - left["started"]) * 1000
            for left, right in zip(events, events[1:])]
    native_phases = defaultdict(list)
    for event in events:
        for phase, milliseconds in event.get("delivery", {}).get("timings_ms", {}).items():
            native_phases[phase].append(milliseconds)
    return sequence, {
        "status": sequence.status, "error": sequence.error,
        "clicks": len(events), "requested_interval_ms": 1,
        "dispatch_interval_median_ms": statistics.median(gaps) if gaps else None,
        "dispatch_intervals_ms": gaps, "elapsed_seconds": sequence.elapsed,
        "rpcs": {name: {"median_ms": statistics.median(times), "samples_ms": times}
                 for name, times in phases.items()},
        "native_phase_medians_ms": {phase: statistics.median(times)
                                    for phase, times in native_phases.items()},
        "routes": sorted({event["delivery"].get("route") or event["delivery"].get("path") or "unknown"
                          for event in events if "delivery" in event}),
    }


def fixture_events(log, total):
    deadline = time.monotonic() + 2
    events = []
    while time.monotonic() < deadline and len(events) < total:
        if log.exists():
            events = [json.loads(line) for line in log.read_text().splitlines(keepends=True) if line.endswith("\n")]
        if len(events) < total:
            time.sleep(.02)
    return events


def received_interval(events):
    return statistics.median((right["time"] - left["time"]) * 1000
                             for left, right in zip(events, events[1:]))


def profile_timeline(command):
    results = {}
    button_log = OUT / "button-events.jsonl"
    canvas_log = OUT / "canvas-events.jsonl"
    if button_log.exists() or canvas_log.exists():
        raise ValueError("Use a fresh output directory for the fixture event logs")

    def save(name, case):
        results[name] = case
        (OUT / "timeline-profile.json").write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps({name: {key: value for key, value in case.items() if key != "dispatch_intervals_ms"
                                 and key != "rpcs"}}), flush=True)

    with Computer(command=command, companion=False) as computer:
        with launched_fixture(computer, "Tobkiri Fixture A", "--profile-timeline", "--single",
                              "--event-log", str(button_log)) as window:
            total = 0
            for name, speed, keys, samples in (("button_fast_same", "fast", "A", 12),
                                              ("button_fast_alternating", "fast", "AB", 12),
                                              ("button_normal_alternating", "normal", "AB", 6)):
                window.set_cursor_speed(speed)
                state = window.observe()
                points = [state.find(key, role="AXButton").point for key in keys]
                _, case = profile_sequence(window, state, [(point.x, point.y) for point in points], samples)
                events = fixture_events(button_log, total + samples)[total:]
                case["received"] = "".join(event["button"] for event in events)
                if len(events) > 1:
                    case["fixture_interval_median_ms"] = received_interval(events)
                save(name, case)
                assert case["status"] == "completed" and case["received"] == keys * (samples // len(keys)), name
                assert all(event["window_number"] == window.surface[1] for event in events)
                total += samples
        with launched_fixture(computer, "Tobkiri Drawing Fixture", "--profile-timeline", "--drawing",
                              "--event-log", str(canvas_log)) as window:
            state = window.observe()
            with Image.open(BytesIO(state.image)) as image:
                points = [(int(image.width * ratio), image.height // 2) for ratio in (.35, .65)]
                # The drawing fixture's wide white panel is not an actionable AX
                # element. Check the actual captured panel before using its pixels.
                rgb = image.convert("RGB")
                assert all(min(rgb.getpixel(point)) >= 245 for point in points)
            _, case = profile_sequence(window, state, points, 12)
            events = fixture_events(canvas_log, 24)
            presses = [event for event in events if event["event"] == "down"]
            case["received"] = len(presses)
            if len(presses) > 1:
                case["fixture_interval_median_ms"] = received_interval(presses)
            save("canvas_fast_alternating", case)
            assert case["status"] == "completed" and [event["event"] for event in events] == ["down", "up"] * 12
            assert max(event["x"] for event in presses[::2]) < min(event["x"] for event in presses[1::2])
            assert all(event["window_number"] == window.surface[1] for event in events)


def probe_file_sheet(command):
    directory = OUT / "fixture-files"
    directory.mkdir(exist_ok=True)
    (directory / "fixture-note.txt").write_text("Tobkiri file selection fixture\n")
    with Computer(command=command, companion=False) as computer:
        with launched_fixture(computer, "Tobkiri File Fixture",
                              "--single", "--file-sheet-directory", str(directory)) as window:
            state = window.observe(screenshot=False)
            window.click(state.find("Choose Fixture File", role="AXButton"), readback="ax")
            deadline = time.monotonic() + 7
            while time.monotonic() < deadline:
                rows = [row for row in computer.windows(pid=window.surface[0])
                        if row["is_on_screen"] and row["window_id"] != window.surface[1]]
                if rows:
                    break
                time.sleep(.1)
            facts = {"parent": window.target, "panels": []}
            for row in rows:
                panel = computer.window(pid=row["pid"], window_id=row["window_id"], name="file-sheet")
                try:
                    observed = panel.observe(screenshot=False, max_elements=400)
                    facts["panels"].append({
                        "window_id": row["window_id"], "title": row["title"],
                        "routes": observed.raw.get("background_input"),
                        "roles": [element.role for element in observed.elements[:12]],
                        "matched_file": bool(observed.find_all("fixture-note.txt")),
                    })
                finally:
                    panel.close()
            parent = window.observe(screenshot=False, max_elements=450)
            facts["parent_sheets"] = [element.label for element in parent.elements if element.role == "AXSheet"]
            canceled = parent.find_all("Cancel", role="AXButton")
            if len(canceled) == 1:
                try:
                    dismissal = window.click(canceled[0], readback="ax")
                    facts["parent_cancel"] = dismissal.delivery
                    facts["dismissed"] = not dismissal.observation.find_all(role="AXSheet")
                except ComputerError as error:
                    facts["cancel_error"] = {"code": error.code, "message": str(error)}
            (OUT / "file-sheet.json").write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(facts, ensure_ascii=False), flush=True)
            assert facts.get("dismissed"), "The file sheet must accept a semantic action through its exact parent"


def measure_readback(command):
    phases = {"same": defaultdict(list), "ax": defaultdict(list)}
    with Computer(command=command, companion=False) as computer:
        with launched_fixture(computer, "Tobkiri Fixture A", "--single") as window:
            transport = computer.transport
            call = transport.call
            action_thread = threading.get_ident()
            mode = None

            def timed_call(name, arguments=None):
                started = time.perf_counter_ns()
                try:
                    return call(name, arguments)
                finally:
                    if mode and threading.get_ident() == action_thread:
                        phases[mode][name].append((time.perf_counter_ns() - started) / 1e6)

            transport.call = timed_call
            try:
                for index in range(12):
                    requested = "same" if index % 2 == 0 else "ax"
                    state = window.observe()
                    field = state.find("Name", role="AXTextField")
                    value = f"Fixture value {index}"
                    mode = requested
                    started = time.perf_counter_ns()
                    result = window.set_value(field, value, readback=mode)
                    phases[mode]["total"].append((time.perf_counter_ns() - started) / 1e6)
                    mode = None
                    assert result.observation.find("Name", role="AXTextField").value == value
                    assert (result.observation.image is not None) == (requested == "same")
            finally:
                transport.call = call
    report = {mode: {name: {"median_ms": round(statistics.median(values), 2), "samples": len(values)}
                     for name, values in timings.items()} for mode, timings in phases.items()}
    (OUT / "readback.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


def check_multiwindow(command, *, electron=False):
    executable = None
    arguments = ("--overlapping-pair",)
    if electron:
        executable = ROOT.parent / "companion/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
        arguments = (str(ROOT / "tests/fixtures/ElectronComputerFixture.cjs"), str(OUT / "profile"))
    with Computer(command=command, companion=False) as computer:
        with launched_fixture(computer, "Tobkiri Overlap A", *arguments, executable=executable) as first:
            pid = first.surface[0]
            second = computer.window(pid=pid, title="Tobkiri Overlap B")
            rows = {row["window_id"]: row for row in computer.windows(pid=pid)}
            assert rows[first.surface[1]]["bounds"] == rows[second.surface[1]]["bounds"]
            report = {"driver": computer.transport.server_info["version"], "toolkit": "Electron" if electron else "AppKit",
                      "overlapping": True}
            try:
                for window, key in ((first, "x"), (second, "y")):
                    state = window.observe(screenshot=False)
                    if electron and not state.find_all("Name", role="AXTextField"):
                        state = window.wait_for(lambda view: view.find_all("Name", role="AXTextField"), timeout=4)
                    result = window.press_key(key, target=state.find("Name", role="AXTextField"), readback="ax")
                    assert result.observation.find("Name", role="AXTextField").value == key
                assert first.observe(screenshot=False).find("Name", role="AXTextField").value == "x"
                report["separate_key_delivery"] = True
                second_count = count(second.observe(screenshot=False))
                state = first.observe()
                button = state.find("Increment", role="AXButton")
                clicked = first.click(state.point(button.point.x, button.point.y), readback="ax")
                first_after = count(clicked.observation)
                if first_after == count(state):
                    first_after = count(first.observe(screenshot=False))
                report["pixel_counts"] = {"target": first_after - count(state),
                                          "sibling": count(second.observe(screenshot=False)) - second_count}
                assert report["pixel_counts"]["sibling"] == 0
                report["exact_pixel_delivery"] = first_after == count(state) + 1
                if electron and not report["exact_pixel_delivery"]:
                    state = first.observe(screenshot=False)
                    clicked = first.click(state.find("Increment", role="AXButton"), readback="ax")
                    assert count(clicked.observation) == first_after + 1
                    assert count(second.observe(screenshot=False)) == second_count
                    report["exact_semantic_delivery"] = True
                else:
                    assert report["exact_pixel_delivery"]
            finally:
                (OUT / "multiwindow.json").write_text(json.dumps(report, indent=2) + "\n")
                print(json.dumps(report), flush=True)
                second.close()


if args.probe_file_sheet:
    probe_file_sheet(command)
    raise SystemExit(0)
if args.measure_readback:
    measure_readback(command)
    raise SystemExit(0)
if args.check_multiwindow or args.check_electron_multiwindow:
    check_multiwindow(command, electron=args.check_electron_multiwindow)
    raise SystemExit(0)
if args.profile_timeline:
    profile_timeline(command)
    raise SystemExit(0)


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
