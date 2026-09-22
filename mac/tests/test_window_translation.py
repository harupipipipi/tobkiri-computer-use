import threading
import time

import pytest

from tobkiri_computer_use import Computer, ComputerError
from tobkiri_computer_use.server import ToolService
from conftest import FakeTransport


def window(c, wid=10):
    return c.window(pid=7, window_id=wid)


def test_idle_cursor_follows_translation_without_changing_observation_or_input(rig):
    c, t = rig; w = window(c); s = w.observe(max_dimension=400)
    w.move(s.find("Increment")); before_calls = len(t.calls)
    t.bounds.update(x=-1234, y=650)
    c._cursors.tick()
    assert t.positions[w.session] == {"x": -1144, "y": 710}
    assert c._latest[w.surface] == s.id
    assert c.cursor_status()[0]["local_screen_point"] == [90, 60]
    assert not any(n in ("get_window_state", "click", "press_key", "bring_to_front") for n, _ in t.calls[before_calls:])
    assert not any(n == "set_agent_cursor_enabled" for n, _ in t.calls[before_calls:])
    assert all(a["target"] == w.target and "scope" not in a for n, a in t.calls[before_calls:] if n == "move_cursor")


def test_repeated_translations_keep_point_zoom_and_semantic_identity(rig):
    c, t = rig; w = window(c); s = w.observe(max_dimension=400)
    element = s.find("Increment"); z = s.zoom([40, 20, 140, 100], scale=2)
    p = z.point(100, 80)
    assert (p.x, p.y) == (90, 60)
    for x, y in [(-1000, 200), (600, -500), (-100, 0)]:
        t.bounds.update(x=x, y=y)
        w.move(element)
        assert c._latest[w.surface] == s.id
        assert w._last.frame.x == x
        assert s.frame.x == -800  # Original image metadata was not mutated.
    w.click(p)
    sent = next(a for n, a in t.calls if n == "click")
    assert (sent["x"], sent["y"]) == (90, 60)
    assert t.cached_frames[10]["x"] == -100
    assert t.counts == {10: 1, 11: 0}


def test_translation_remaps_old_element_to_new_native_token(rig):
    c, t = rig; w = window(c); s = w.observe(); e = s.find("Increment")
    t.bounds["y"] += 300
    w.click(e)
    sent = next(a for n, a in t.calls if n == "click")
    assert sent["element_token"] != e.token
    assert sent["element_token"].endswith(":1")


@pytest.mark.parametrize("change", ["resize", "scale", "layout"])
def test_geometry_or_layout_change_refuses_old_points(rig, change):
    c, t = rig; w = window(c); s = w.observe()
    t.bounds["x"] += 200
    if change == "resize": t.bounds["width"] += 100
    if change == "scale": t.image_scale = .75
    if change == "layout": t.element_shift = 20
    with pytest.raises(ComputerError) as exc: w.click(s.find("Increment").point)
    assert exc.value.code == "stale_geometry"
    assert not any(n == "click" for n, _ in t.calls)


def test_new_sibling_overlap_is_checked_at_translated_origin(rig):
    c, t = rig; w = window(c); s = w.observe()
    t.bounds["x"] += 700; t.sibling_offset = 0
    with pytest.raises(ComputerError) as exc: w.click(s.find("Increment").point)
    assert exc.value.code == "overlapping_window"
    assert not any(n == "click" for n, _ in t.calls)


def test_resize_hides_overlay_and_requires_new_anchor_even_if_size_reverts(rig):
    c, t = rig; w = window(c); s = w.observe(); w.move(s.find("Increment"))
    t.bounds["width"] += 100; c._cursors.tick()
    assert not t.enabled[w.session]
    assert c._cursors.status(w)["phase"] == "geometry_changed"
    t.bounds["width"] -= 100; c._cursors.tick()
    assert not t.enabled[w.session]
    with pytest.raises(ComputerError): w.click(s.find("Increment").point)
    w.move(w.observe().find("Increment"))
    assert t.enabled[w.session]


def test_hidden_window_cursor_hides_and_reappears_at_new_origin(rig):
    c, t = rig; w = window(c); s = w.observe(); w.move(s.find("Increment"))
    t.visible = False; t.bounds["y"] += 100; c._cursors.tick()
    assert not t.enabled[w.session]
    t.visible = True; c._cursors.tick()
    assert t.enabled[w.session]
    assert t.positions[w.session]["y"] == 260


def test_missing_window_never_retargets_another_window(rig):
    c, t = rig; w = window(c); w.observe(); t.include_windows = False
    c._cursors.tick()
    assert c._cursors.status(w)["phase"] == "window_unavailable"
    assert not t.enabled[w.session]
    t.include_windows = True; c._cursors.tick()
    assert not t.enabled[w.session]


def test_two_cursors_keep_independent_window_relative_anchors(rig):
    c, t = rig; a = window(c); b = window(c, 11)
    a.move(a.observe(max_dimension=400).point(20, 30))
    b.move(b.observe(max_dimension=800).point(100, 140))
    t.bounds.update(x=-200, y=-50); c._cursors.tick()
    assert t.positions[a.session] == {"x": -180, "y": -20}
    assert t.positions[b.session] == {"x": 350, "y": 20}


def test_follower_errors_are_visible_and_do_not_trigger_input_retries(rig):
    c, t = rig; w = window(c); w.observe(); t.error = "move_cursor"
    t.bounds["x"] += 50; c._cursors.tick()
    status = c._cursors.status(w)
    assert status["phase"] == "error" and status["error"]
    moves = sum(n == "move_cursor" for n, _ in t.calls)
    c._cursors.tick()
    assert sum(n == "move_cursor" for n, _ in t.calls) == moves
    assert not any(n == "click" for n, _ in t.calls)


def test_raw_custom_cursor_does_not_rebind_the_default_overlay(rig):
    c, t = rig
    c.tool("get_window_state", {"pid": 7, "window_id": 10, "session": "raw"})
    before = c.cursor_status()[0]["local_screen_point"]
    start = len(t.calls)
    c.tool("move_cursor", {"target": {"kind": "window", "pid": 7, "window_id": 10},
                           "session": "raw", "cursor_id": "custom", "x": -750, "y": 150})
    assert c.cursor_status()[0]["local_screen_point"] == before
    moves = [a for n, a in t.calls[start:] if n == "move_cursor"]
    assert len(moves) == 1 and moves[0]["cursor_id"] == "custom"


def test_background_follow_thread_runs_and_stops_with_computer():
    t = FakeTransport()
    with Computer(transport=t, cursor_coordinates="screen_points", cursor_follow_interval=.02) as c:
        w = window(c); w.move(w.observe().point(20, 20))
        t.bounds["x"] += 100
        deadline = time.monotonic()+2
        while t.positions[w.session]["x"] != -690 and time.monotonic() < deadline:
            time.sleep(.01)
        assert t.positions[w.session]["x"] == -690
        worker = c._cursors._thread
    assert not worker.is_alive()
    calls = len(t.calls); time.sleep(.03)
    assert len(t.calls) == calls


@pytest.mark.parametrize("semantic", [False, True])
def test_raw_mcp_window_inputs_refresh_translation_without_changing_local_coords(rig, semantic):
    c, t = rig
    raw = c.tool("get_window_state", {"pid": 7, "window_id": 10, "include_screenshot": True, "max_dimension": 400})["structuredContent"]
    args = {"pid": 7, "window_id": 10}
    args.update(element_token=raw["elements"][1]["element_token"]) if semantic else args.update(x=90, y=60)
    t.bounds.update(x=-200, y=400)
    result = c.tool("click", args)
    assert result["structuredContent"]["effect"] == "unverifiable"
    sent = next(a for n, a in t.calls if n == "click")
    if semantic:
        assert sent["element_token"] != args["element_token"]
        assert sent["element_token"].endswith(":1")
    else:
        assert (sent["x"], sent["y"]) == (90, 60)
    t.bounds["y"] += 50; c._cursors.tick()
    assert t.positions[None] == {"x": -110, "y": 510}
    assert t.cached_frames[10]["y"] == 400


def test_raw_session_switches_its_anchor_to_the_explicit_window(rig):
    c, t = rig
    for wid in (10, 11):
        c.tool("get_window_state", {"pid": 7, "window_id": wid, "session": "raw"})
    t.bounds["x"] += 100; c._cursors.tick()
    assert c.cursor_status()[0]["target"]["window_id"] == 11
    assert t.positions["raw"]["x"] == 0


def test_cursor_status_tool_does_not_create_or_move_a_cursor(rig):
    c, t = rig; service = ToolService(c)
    result = service.call("tobkiri_cursor", {"pid": 7, "window_id": 10, "action": "status"})
    assert result["structuredContent"] == {"cursors": []}
    assert not t.calls


def test_stationary_named_cursors_survive_idle_ttl_without_input(rig):
    c, t = rig
    now = [0.0]
    c._cursors._clock = lambda: now[0]
    a, b = window(c), window(c, 11)
    a.observe(); b.observe()
    last_activity = {a.session: 0.0, b.session: 0.0}
    native_call = t._call

    def expiring_cursor(name, args):
        sid = args.get("session")
        if sid in last_activity and name == "get_agent_cursor_state":
            if now[0] - last_activity[sid] >= 300:
                raise ComputerError("session_ended", "idle timeout")
            last_activity[sid] = now[0]
        return native_call(name, args)

    t._call = expiring_cursor
    before = len(t.calls)
    observation_ids = dict(c._latest)
    for second in range(1, 661):
        now[0] = float(second)
        c._cursors.tick()
    later = t.calls[before:]
    assert last_activity == {a.session: 660.0, b.session: 660.0}
    assert all(n in ("list_windows", "get_agent_cursor_state") for n, _ in later)
    assert sum(n == "get_agent_cursor_state" for n, _ in later) == 22
    assert c._latest == observation_ids
    assert all(row["phase"] == "following" for row in c.cursor_status())


def test_cursor_state_poll_reports_ended_session_without_revival_or_retry(rig):
    c, t = rig
    now = [0.0]
    c._cursors._clock = lambda: now[0]
    w = window(c); w.observe()
    t.error = "get_agent_cursor_state"
    before = len(t.calls)
    now[0] = 60.0; c._cursors.tick()
    assert c._cursors.status(w)["phase"] == "error"
    assert c._cursors.status(w)["error"]
    now[0] = 120.0; c._cursors.tick()
    later = t.calls[before:]
    assert sum(n == "get_agent_cursor_state" for n, _ in later) == 1
    assert all(n in ("list_windows", "get_agent_cursor_state", "set_agent_cursor_enabled")
               for n, _ in later)
    assert all(not args["enabled"] for n, args in later if n == "set_agent_cursor_enabled")


@pytest.mark.parametrize("inactive", ["closed", "resized", "missing"])
def test_inactive_cursor_anchors_are_not_kept_alive(rig, inactive):
    c, t = rig
    now = [0.0]
    c._cursors._clock = lambda: now[0]
    w = window(c); w.observe()
    if inactive == "closed":
        w.close()
    elif inactive == "resized":
        t.bounds["width"] += 100
    else:
        t.include_windows = False
    c._cursors.tick()
    before = len(t.calls)
    now[0] = 600.0; c._cursors.tick()
    assert not any(n == "get_agent_cursor_state" for n, _ in t.calls[before:])


def test_raw_implicit_cursor_poll_keeps_implicit_session_and_observation(rig):
    c, t = rig
    now = [0.0]
    c._cursors._clock = lambda: now[0]
    c.tool("get_window_state", {"pid": 7, "window_id": 10})
    before = len(t.calls)
    now[0] = 60.0; c._cursors.tick()
    polls = [args for name, args in t.calls[before:] if name == "get_agent_cursor_state"]
    assert polls == [{}]  # Native registry supplies the transport's implicit session.
    assert c.cursor_status()[0]["phase"] == "following"


def test_hidden_cursor_state_poll_never_shows_or_moves_it(rig):
    c, t = rig
    now = [0.0]
    c._cursors._clock = lambda: now[0]
    w = window(c); w.observe()
    t.visible = False; c._cursors.tick()
    before = len(t.calls)
    now[0] = 60.0; c._cursors.tick()
    assert [name for name, _ in t.calls[before:]] == ["list_windows", "get_agent_cursor_state"]
    assert c._cursors.status(w)["phase"] == "window_hidden"
    assert not t.enabled[w.session]
