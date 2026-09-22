import threading
import pytest
from tobkiri_computer_use import ClickStep, Computer, ComputerError
from tobkiri_computer_use.server import ToolService, handle_rpc, HELPERS


class Clock:
    def __init__(self): self.now = 100.; self.cancelled = False
    def monotonic(self): return self.now
    def wait(self, seconds): self.now += seconds; return self.cancelled
    def is_set(self): return self.cancelled


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr("tobkiri_computer_use.timeline.time.monotonic", clock.monotonic)
    return clock


def setup(rig):
    c, t = rig
    w = c.window(pid=7, window_id=10)
    s = w.observe(max_dimension=400)
    t.calls.clear()
    return c, t, w, s


def test_timed_clicks_use_multiple_cursors_and_only_final_observation(rig, clock):
    c, t, w, s = setup(rig)
    right = c.mouse("right", pid=7, window_id=10)
    result = w.timeline([ClickStep(0., s.point(50, 50)), ClickStep(.2, s.point(60, 50), right),
                         ClickStep(.4, s.point(50, 50))], stop_event=clock)
    assert result.status == "completed" and t.counts[10] == 3
    assert [e["started"] for e in result.events] == pytest.approx([0, .2, .4])
    assert [e["cursor"] for e in result.events] == [w.session, right.session, w.session]
    assert all(e["delivery"]["effect"] == "unverifiable" for e in result.events)
    assert sum(n == "get_window_state" for n, _ in t.calls) == 1
    assert sum(n == "move_cursor" for n, _ in t.calls) == 3
    assert t.positions[w.session] == dict(zip(("x", "y"), s.frame.to_screen(50, 50)))
    assert t.positions[right.session] == dict(zip(("x", "y"), s.frame.to_screen(60, 50)))
    assert result.observation.frame == s.frame
    assert len(result.observation.marks) == 3
    for n, a in t.calls:
        if n == "click": assert a["target"] == w.target and a["delivery_mode"] == "background"


@pytest.mark.parametrize("bad", [float("nan"), -1, 121])
def test_invalid_schedule_sends_no_input(rig, clock, bad):
    c, t, w, s = setup(rig)
    with pytest.raises(ValueError):
        w.timeline([ClickStep(0, s.point(50, 50)), ClickStep(bad, s.point(50, 50))], stop_event=clock)
    assert not any(n == "click" for n, _ in t.calls)


def test_foreign_or_stale_point_is_rejected_before_first_event(rig, clock):
    c, t, w, s = setup(rig)
    b = c.window(pid=7, window_id=11); other = b.observe()
    for point in (other.point(50, 50), s.point(50, 50)):
        if point.surface == w.surface: w.observe()
        with pytest.raises(ComputerError):
            w.timeline([ClickStep(0, point)], stop_event=clock)
    assert not any(n == "click" for n, _ in t.calls)


@pytest.mark.parametrize("change,expected", [("resize", "stale_geometry"), ("overlap", "overlapping_window"),
                                           ("hidden", "stale_geometry"), ("cancel", None)])
def test_changed_target_or_cancel_stops_remaining_events(rig, clock, change, expected):
    c, t, w, s = setup(rig); original = t.call
    def call(name, args=None):
        result = original(name, args)
        if name == "click":
            if change == "resize": t.bounds["width"] += 10
            elif change == "overlap": t.sibling_offset = 0
            elif change == "hidden": t.visible = False
            else: clock.cancelled = True
        return result
    t.call = call
    result = w.timeline([ClickStep(0, s.point(50, 50)), ClickStep(.2, s.point(50, 50))], stop_event=clock)
    assert t.counts[10] == 1
    if expected: assert result.status == "stopped" and result.error["code"] == expected
    else: assert result.status == "cancelled"


def test_translation_refreshes_native_frame_without_changing_local_pixels(rig, clock):
    c, t, w, s = setup(rig); original = t.call
    def call(name, args=None):
        result = original(name, args)
        if name == "click" and t.counts[10] == 1: t.bounds["x"] += 100
        return result
    t.call = call
    result = w.timeline([ClickStep(0, s.point(50, 50)), ClickStep(.2, s.point(50, 50))], stop_event=clock)
    assert result.status == "completed"
    clicks = [a for n, a in t.calls if n == "click"]
    assert [(a["x"], a["y"]) for a in clicks] == [(50, 50)]*2
    assert any(n == "get_window_state" and a.get("include_accessibility_tree") is False for n, a in t.calls)


def test_slow_driver_does_not_emit_catchup_burst(rig, clock):
    c, t, w, s = setup(rig); original = t.call
    def call(name, args=None):
        result = original(name, args)
        if name == "click": clock.now += .8
        return result
    t.call = call
    result = w.timeline([ClickStep(0, s.point(50, 50)), ClickStep(.1, s.point(50, 50))], stop_event=clock)
    assert t.counts[10] == 1 and result.error["code"] == "timeline_late"


def test_native_error_is_not_retried_and_marks_unknown_outcome(rig, clock):
    c, t, w, s = setup(rig); t.error = "click"
    result = w.timeline([ClickStep(0, s.point(50, 50)), ClickStep(.1, s.point(50, 50))], stop_event=clock)
    assert result.status == "stopped"
    assert len(result.events) == 1 and "unknown" in result.events[0]["outcome"]
    assert sum(n == "click" for n, _ in t.calls) == 1


def test_explicit_stretch_finishes_and_reports_shift_without_catchup(rig, clock):
    c, t, w, s = setup(rig); original = t.call
    def call(name, args=None):
        result = original(name, args)
        if name == "click" and t.counts[10] == 1: clock.now += .8
        return result
    t.call = call
    result = w.timeline([ClickStep(i*.1, s.point(50, 50)) for i in range(3)], on_late="stretch", stop_event=clock)
    assert result.status == "completed" and t.counts[10] == 3
    assert [e["started"] for e in result.events] == pytest.approx([0, .8, .9])
    assert result.events[-1]["schedule_shift_seconds"] == pytest.approx(.7)


def test_default_fast_profile_is_session_local_and_positive_not_zero(rig):
    c, t = rig; a = c.mouse("a", pid=7, window_id=10); b = c.mouse("b", pid=7, window_id=11)
    calls = [a for n, a in t.calls if n == "set_agent_cursor_motion"]
    assert {args["session"] for args in calls} == {a.session, b.session}
    assert all(args["glide_duration_ms"] == 1 and args["dwell_after_click_ms"] == 0 for args in calls)
    a.set_cursor_speed("normal")
    assert t.calls[-1][1]["glide_duration_ms"] == 0
    assert not any(n == "set_config" for n, _ in t.calls)


def test_new_cursor_is_enabled_before_first_visual_move(rig):
    c, t = rig; w = c.window(pid=7, window_id=10); t.calls.clear()
    w.observe()
    enabled = next(i for i, (n, a) in enumerate(t.calls) if n == "set_agent_cursor_enabled" and a["enabled"])
    moved = next(i for i, (n, a) in enumerate(t.calls) if n == "move_cursor")
    assert enabled < moved


def test_mcp_timeline_and_cursor_speed(rig):
    c, t = rig; service = ToolService(c)
    def call(name, **args):
        return handle_rpc(service, {"method": "tools/call", "params": {"name": name, "arguments": args}})
    s = call("tobkiri_observe", pid=7, window_id=10)["structuredContent"]
    result = call("tobkiri_timeline", pid=7, window_id=10, observation_id=s["observation_id"],
                  steps=[{"at": 0, "point": [50, 50], "cursor": "left"}], include_image=False)
    assert result["structuredContent"]["status"] == "completed" and t.counts[10] == 1
    assert len(HELPERS) == 11
    call("tobkiri_cursor", pid=7, window_id=10, action="speed", profile="normal")
    assert t.calls[-1][0] == "set_agent_cursor_motion"
