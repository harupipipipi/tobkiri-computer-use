"""Opt-in latency comparison on the dedicated TobkiriFixture only."""
from collections import defaultdict
import json
from pathlib import Path
import re
import statistics
import time

from tobkiri_computer_use import Computer, ClickStep
from tobkiri_computer_use.transport import structured

ROOT = Path(__file__).resolve().parents[1]
report = {"scope": "Dedicated TobkiriFixture only", "checks": {}}


def count(s): return int(re.search(r"Count: (\d+)", s.tree).group(1))


with Computer(cursor_profile=None) as c:
    a = c.window(app="TobkiriFixture", title="Tobkiri Fixture A", name="latency-left")
    right = c.mouse("latency-right", pid=a.surface[0], window_id=a.surface[1])
    b = c.window(app="TobkiriFixture", title="Tobkiri Fixture B", name="latency-other-window")
    report["driver"] = c.transport.server_info
    report["target"] = a.target
    samples = []
    original = c.transport.call
    def measured(name, args=None):
        start = time.perf_counter()
        try: return original(name, args)
        finally: samples.append((name, time.perf_counter()-start))
    c.transport.call = measured
    for mode in ("normal", "fast"):
        a.set_cursor_speed(mode)
        s = a.observe(); n = count(s)
        p = s.find("Increment").point
        points = [(p.x-65, p.y), (p.x+65, p.y)]
        durations = []; samples.clear()
        for i in range(6):
            started = time.perf_counter()
            result = a.click(s.point(*points[i % 2]))
            durations.append(time.perf_counter()-started)
            s = result.observation
        assert count(s) == n+6
        totals = defaultdict(lambda: {"count": 0, "seconds": 0})
        for name, elapsed in samples:
            totals[name]["count"] += 1; totals[name]["seconds"] += elapsed
        report[mode] = {"per_click_seconds": durations, "median_seconds": statistics.median(durations), "rpc": dict(totals)}
    report["checks"]["normal_and_fast_clicks_all_delivered_once"] = True

    right.set_cursor_speed("fast")
    s = a.observe(); n = count(s); samples.clear()
    steps = [ClickStep(i*.25, s.point(*points[i % 2]), right if i % 2 else a) for i in range(12)]
    result = a.timeline(steps, max_lateness=.22)
    assert result.status == "completed", result.to_dict()
    assert count(result.observation) == n+12
    assert sum(name == "get_window_state" for name, _ in samples) == 1
    assert sum(name == "move_cursor" for name, _ in samples) == 12
    assert {e["cursor"] for e in result.events} == {a.session, right.session}
    report["timeline"] = {k: v for k, v in result.to_dict().items() if k != "observation"}
    report["timeline"]["max_dispatch_lateness_seconds"] = max(e["lateness_seconds"] for e in result.events)
    report["checks"]["four_hz_timeline_two_cursors_twelve_clicks"] = True
    report["checks"]["one_final_capture_one_fast_cursor_move_per_step"] = True
    report["motion_readback"] = structured(a._call("get_agent_cursor_state"))["motion"]
    assert report["motion_readback"]["glide_duration_ms"] == 1
    for owner, coordinates in ((a, points[0]), (right, points[1])):
        state = structured(owner._call("get_agent_cursor_state"))
        expected = s.frame.to_screen(*coordinates)
        assert abs(state["position"]["x"]-expected[0]) < 1 and abs(state["position"]["y"]-expected[1]) < 1
    report["checks"]["both_cursor_positions_match_last_input"] = True
    result.observation.save(ROOT/"artifacts/latency-result.png")

    b.set_cursor_speed("fast")
    sa, sb = a.observe(), b.observe(); na, nb = count(sa), count(sb)
    epoch = time.monotonic()+.5
    results = c.parallel(
        lambda: a.timeline([ClickStep(i*.6, sa.find("Increment").point) for i in range(4)], start_at=epoch, max_lateness=.5),
        lambda: b.timeline([ClickStep(i*.6, sb.find("Increment").point) for i in range(4)], start_at=epoch, max_lateness=.5),
    )
    for r in results:
        if isinstance(r, Exception): raise r
        assert r.status == "completed", r.to_dict()
    assert count(results[0].observation) == na+4 and count(results[1].observation) == nb+4
    report["checks"]["parallel_windows_share_python_start_clock"] = True
    report["parallel_events"] = [r.events for r in results]

(ROOT/"artifacts/latency-acceptance.json").write_text(json.dumps(report, indent=2)+"\n")
print(json.dumps({"checks": report["checks"], "normal_median_seconds": report["normal"]["median_seconds"],
                  "fast_median_seconds": report["fast"]["median_seconds"],
                  "timeline_max_dispatch_lateness_seconds": report["timeline"]["max_dispatch_lateness_seconds"]}, indent=2))
