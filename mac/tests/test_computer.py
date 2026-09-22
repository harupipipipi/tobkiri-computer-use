from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from PIL import Image
import pytest

from tobkiri_computer_use import ComputerError


def window(c, wid=10):
    return c.window(pid=7,window_id=wid)


def test_selection_requires_unique_window(rig):
    c, _ = rig
    with pytest.raises(ComputerError, match="exact window"):
        c.window(app="Fixture")
    assert c.window(app="Fixture",title="10").surface == (7,10)


def test_observe_extracts_coords_filters_menu_but_keeps_text(rig):
    c, t = rig
    s = window(c).observe()
    assert s.find("Increment").point.x == 180
    assert s.find("Increment").point.y == 120
    assert s.find("Offscreen").point is None
    assert "Recent private" not in s.tree
    assert "Count: 0" in s.tree
    assert not s.find_all("Menu")


def test_old_elements_and_points_refused_before_input(rig):
    c, t = rig
    w=window(c); old=w.observe(); fresh=w.observe()
    for target in (old.find("Increment"), old.point(20,20)):
        with pytest.raises(ComputerError) as exc:
            w.click(target)
        assert exc.value.code == "stale_observation"
    assert not any(n == "click" for n,_ in t.calls)
    assert w.click(fresh.find("Increment")).observation.find("Name")


def test_cross_window_points_refused(rig):
    c,t=rig; a=window(c); b=window(c,11)
    point=a.observe().point(10,10); b.observe()
    with pytest.raises(ComputerError): b.click(point)
    assert not any(n == "click" for n,_ in t.calls)


def test_moved_window_keeps_local_point_and_refreshes_native_frame(rig):
    c,t=rig; w=window(c); s=w.observe()
    t.bounds["x"] += 200
    w.click(s.point(10,10))
    sent=next(a for n,a in t.calls if n=="click")
    assert (sent['x'],sent['y']) == (10,10)
    assert sent['target']['window_id']==10
    assert sum(n=='get_window_state' for n,_ in t.calls)==3


def test_no_screenshot_no_pixels_semantics_still_work(rig):
    c,t=rig; w=window(c); s=w.observe(screenshot=False)
    assert s.find("Increment").point is None
    with pytest.raises(ComputerError): s.point(1,1)
    assert w.click(s.find("Increment")).delivery["effect"] == "unverifiable"


def test_unknown_effect_preserved_and_fresh_diff_returned(rig):
    c,t=rig; w=window(c)
    r=w.click("Increment",expect=[{"window":{"exists":True}}])
    assert r.delivery["effect"] == "unverifiable"
    assert r.verification["status"] == "unknown"
    assert "+  - Count: 1" in r.observation.changes
    assert len(r.observation.marks) == 1
    assert r.observation.marks[0]["effect"] == "unverifiable"


def test_marks_are_red_image_only_and_bounded(rig):
    c,t=rig; w=window(c); s=w.click("Increment").observation
    raw=Image.open(BytesIO(s.image)); marked=Image.open(BytesIO(s.png()))
    assert raw.getpixel((180,120)) == (255,255,255)
    assert marked.getpixel((180,120)) == (239,51,64)
    assert c._history[w.surface].maxlen == 32


def test_zoom_clips_edges_roundtrips_and_expires(rig):
    c,t=rig; w=window(c); s=w.observe()
    z=s.zoom([-10,-20,80,100],scale=2)
    assert (z.crop.output_width,z.crop.output_height) == (160,200)
    assert (z.point(80,100).x,z.point(80,100).y) == (40,50)
    other=s.zoom([100,100,200,200]); assert z.id != other.id
    w.observe()
    with pytest.raises(ComputerError): w.click(z.point(80,100))
    for region in ([10,10,0,0],[900,800,1000,900]):
        with pytest.raises(ComputerError): s.zoom(region)


def test_cursor_maps_pixels_to_screen_points_and_reads_back(rig):
    c,t=rig; w=window(c); s=w.observe(max_dimension=400)
    result=w.move(s.find("Increment"))
    assert result["expected_screen_point"] == [-710,160]
    assert result["position_matches"]
    assert result["pixels_verified"] is False
    sent=next(a for n,a in reversed(t.calls) if n=="move_cursor")
    assert sent["target"] == {"kind":"window","pid":7,"window_id":10}
    assert (sent["x"],sent["y"]) == (-710,160)


def test_unknown_cursor_contract_does_not_send(rig):
    c,t=rig; c.cursor_coordinates=None; w=window(c)
    with pytest.raises(ComputerError) as exc: w.move(w.observe().find("Increment"))
    assert exc.value.code == "cursor_contract_unknown"
    assert not any(n=="move_cursor" for n,_ in t.calls)


def test_distinct_sessions_parallel_independent_windows(rig):
    c,t=rig; a=window(c); b=window(c,11); t.delay=.01
    assert a.session != b.session
    results=c.parallel(lambda:a.click("Increment"),lambda:b.click("Increment"))
    assert all(not isinstance(r,Exception) for r in results)
    assert t.counts == {10:1,11:1}
    assert t.max_active >= 2


def test_same_window_actions_serialize_and_do_not_lose_updates(rig):
    c,t=rig; a=window(c); b=window(c); t.delay=.001
    results=c.parallel(lambda:a.click("Increment"),lambda:b.click("Increment"))
    assert all(not isinstance(r,Exception) for r in results)
    assert t.counts[10] == 2
    assert t.max_active == 1


def test_error_and_async_failure_are_not_silenced(rig):
    c,t=rig; w=window(c); s=w.observe(); t.error="move_cursor"
    with pytest.raises(ComputerError): w.move_async(s.find("Increment")).result()
    t.error="click"
    with pytest.raises(ComputerError): w.click("Increment")
    assert sum(n=="click" for n,_ in t.calls)==1


def test_raw_call_invalidates_helpers_and_preserves_result(rig):
    c,t=rig; w=window(c); s=w.observe()
    assert c.tool("native_example",{"value":"hello"})["structuredContent"] == {"value":"hello"}
    with pytest.raises(ComputerError): w.click(s.find("Increment"))


@pytest.mark.parametrize("name,args", [("list_windows",{}), ("get_config",{}),
                                      ("get_accessibility_tree",{}),
                                      ("get_browser_state",{"pid":7,"window_id":11}),
                                      ("get_recording_state",{})])
def test_raw_read_only_calls_preserve_observed_targets(rig,name,args):
    c,t=rig; w=window(c); s=w.observe()
    c.tool(name,args)
    w.click(s.find("Increment"))
    assert t.counts[10]==1


def test_raw_other_window_snapshot_does_not_invalidate_this_window(rig):
    c,t=rig; a=window(c); b=window(c,11); sa=a.observe(); sb=b.observe()
    c.tool("get_window_state",{"pid":7,"window_id":11})
    a.click(sa.find("Increment"))
    with pytest.raises(ComputerError):b.click(sb.find("Increment"))
    assert t.counts=={10:1,11:0}


def test_changed_page_title_refuses_stale_pixel_click_without_selecting_a_tab(rig):
    c,t=rig; w=window(c); s=w.observe()
    original=t._call
    def changed(name,args):
        result=original(name,args)
        if name=="list_windows":result['structuredContent']['windows'][0]['title']='Another tab'
        return result
    t._call=changed
    with pytest.raises(ComputerError,match="title/page changed"):
        w.click(s.point(180,120))
    assert not any(n=='click' for n,_ in t.calls)


def test_close_ends_only_owned_sessions(rig):
    c,t=rig; a=window(c); b=window(c,11)
    c.close()
    assert {args["session"] for name,args in t.calls if name=="end_session"} == {a.session,b.session}
    assert t.closed


def test_ambiguous_elements_are_not_guessed(rig):
    c,t=rig; s=window(c).observe()
    with pytest.raises(ComputerError) as exc: s.find(role="AXButton")
    assert exc.value.code == "ambiguous_element"


def test_pixel_click_keeps_original_downscaled_frame(rig):
    c,t=rig; w=window(c); s=w.observe(max_dimension=400)
    w.click(s.point(90,60))
    sent=next(a for n,a in t.calls if n=="click")
    assert sent["x"]==90 and sent["y"]==60
    # No new observation may change the driver's scale before dispatch.
    names=[name for name,_ in t.calls]
    assert names[:names.index("click")].count("get_window_state")==1


def test_overlapping_sibling_pixel_input_refused_semantic_still_targets_exact_window(rig):
    c,t=rig; t.sibling_offset=0; w=window(c); s=w.observe()
    with pytest.raises(ComputerError) as exc: w.click(s.find("Increment").point)
    assert exc.value.code == "overlapping_window"
    assert not any(n=="click" for n,_ in t.calls)
    result=w.click(s.find("Increment"))
    assert t.counts == {10:1,11:0}
    assert next(a for n,a in t.calls if n=="click")["window_id"]==10


@pytest.mark.parametrize("status", ["refused","unknown","unavailable"])
def test_unproven_keyboard_delivery_never_reaches_another_window(rig,status):
    c,t=rig; t.keyboard_status=status; w=window(c)
    for operation in (lambda:w.press_key("a"),lambda:w.type_text("Name","danger")):
        with pytest.raises(ComputerError) as exc: operation()
        assert exc.value.code=="keyboard_target_unproven"
    assert not any(n in ("press_key","type_text") for n,_ in t.calls)
    w.set_value("Name","safe exact element")
    assert t.values == {10:"safe exact element",11:""}


def test_offwindow_semantic_elements_refused(rig):
    c,t=rig; w=window(c)
    with pytest.raises(ComputerError) as exc: w.click("Offscreen")
    assert exc.value.code=="outside_window"
    assert not any(n=="click" for n,_ in t.calls)


def test_semantic_scroll_still_checks_pixel_hit_test_on_sibling(rig):
    c,t=rig; t.sibling_offset=0; w=window(c); s=w.observe()
    with pytest.raises(ComputerError) as exc: w.scroll(s.find("Increment"),"down")
    assert exc.value.code=="overlapping_window"
    assert not any(n=="scroll" for n,_ in t.calls)


@pytest.mark.parametrize("action", ["point", "label", "drag", "key"])
def test_automatic_observation_preserves_image_scale_and_element_budget(rig, action):
    c, t = rig; w = window(c)
    s = w.observe(max_dimension=400, max_elements=1000, full_tree=True)
    if action == "point":
        result = w.click(s.find("Increment").point)
    elif action == "label":
        result = w.click("Increment")
    elif action == "drag":
        result = w.drag(s.point(50, 50), s.point(150, 50))
    else:
        result = w.press_key("a")
    assert result.observation.frame == s.frame
    assert any(e.role == "AXMenuBar" for e in result.observation.elements)
    reads = [args for name, args in t.calls if name == "get_window_state"]
    assert all(a["max_dimension"] == 400 and a["max_elements"] == 1000 for a in reads)


def test_default_walk_keeps_controls_after_first_200_nodes(rig, monkeypatch):
    c, t = rig; original = t._call
    def long_page(name, args):
        result = original(name, args)
        if name == "get_window_state":
            raw = result["structuredContent"]
            rows = [e for e in raw["elements"] if e["element_index"] < 4]
            rows.extend({"element_index": i, "role": "AXStaticText", "label": str(i)}
                        for i in range(4, 250))
            button = {**rows[1], "element_index": 250, "label": "Auto Play",
                      "element_token": raw["snapshot_id"] + ":250"}
            rows.append(button)
            raw["elements"] = rows[:args["max_elements"]]
            raw["elements_complete"] = len(raw["elements"]) == len(rows)
        return result
    monkeypatch.setattr(t, "_call", long_page)
    w = window(c)
    limited = w.observe(max_elements=200)
    assert not limited.raw["elements_complete"] and not limited.find_all("Auto Play")
    state = w.observe()
    assert state.raw["elements_complete"]
    result = w.click(state.find("Auto Play"))
    assert result.observation.find("Auto Play").id == 250
    assert t.counts[10] == 1
