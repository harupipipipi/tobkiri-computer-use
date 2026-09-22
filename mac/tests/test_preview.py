from dataclasses import replace
from io import BytesIO

from PIL import Image
import pytest

from tobkiri_computer_use import ComputerError
from tobkiri_computer_use.server import ToolService
from test_server import call


def test_preview_is_local_preserves_source_and_exact_click_point(rig, tmp_path):
    c, t = rig
    w = c.window(pid=7, window_id=10)
    s = w.observe()
    before_calls, original = list(t.calls), s.image
    preview = s.preview(s.point(310, 240))
    assert t.calls == before_calls
    assert s.image == original and not s.marks
    assert preview.point == s.point(310, 240)
    image = Image.open(BytesIO(preview.image))
    assert image.size == (800, 600)
    assert image.getpixel((295, 240)) == (0, 120, 212)
    assert image.getpixel((310, 240)) == (255, 255, 255)
    assert preview.to_dict()["input_sent"] is False
    assert preview.to_dict()["live_target_checked"] is False
    assert preview.to_dict()["effect"] == "not_predicted"
    preview.save(tmp_path / "full.png")
    preview.save(tmp_path / "detail.png", detail=True)
    assert (tmp_path / "detail.png").read_bytes() == preview.detail_image
    # Movement alone does not change the point that was previewed.
    t.bounds["x"] += 200
    w.click(preview.point)
    sent = next(a for n, a in t.calls if n == "click")
    assert (sent["x"], sent["y"]) == (310, 240)


def test_element_center_preview_and_red_history_are_distinct(rig):
    c, t = rig
    w = c.window(pid=7, window_id=10)
    s = w.click("Increment").observation
    before_calls, history = list(t.calls), list(c._history[w.surface])
    preview = s.preview(s.find("Name"))
    assert preview.to_dict()["element"]["label"] == "Name"
    assert preview.to_dict()["point"] == [300, 230]
    assert t.calls == before_calls and list(c._history[w.surface]) == history
    assert Image.open(BytesIO(preview.image)).getpixel((180, 120)) == (239, 51, 64)
    # Preview metadata is returned by value.
    preview.to_dict()["point"][0] = 12345
    assert preview.to_dict()["point"] == [300, 230]


@pytest.mark.parametrize("point", [(0, 0), (799, 599), (799, 0), (0, 599), (0.5, 100.25)])
def test_preview_detail_clips_edges_and_maps_exact_pixel(point, rig):
    c, _ = rig
    s = c.window(pid=7, window_id=10).observe()
    preview = s.preview(s.point(*point), radius=53, scale=2.7)
    d = preview.to_dict()["detail"]
    left, top, right, bottom = d["region"]
    width, height = d["image_size"]
    px, py = d["point"]
    assert 0 <= px < width and 0 <= py < height
    assert (left+px*(right-left)/width, top+py*(bottom-top)/height) == pytest.approx(point)
    assert Image.open(BytesIO(preview.detail_image)).size == (width, height)


def test_zoom_preview_uses_crop_transform_and_source_coordinates(rig):
    c, t = rig
    w = c.window(pid=7, window_id=10)
    s = w.observe(max_dimension=400)
    z = s.zoom([11, 23, 344, 224], scale=3, max_dimension=1000)
    before = list(t.calls)
    preview = z.preview(z.crop.output_width/2, z.crop.output_height/2)
    assert preview.to_dict()["point"] == [177.5, 123.5]
    assert preview.to_dict()["source"]["zoom_id"] == z.id
    assert t.calls == before
    # A preview never renews an old observation or bypasses resize checks.
    t.bounds["width"] += 100
    with pytest.raises(ComputerError):
        w.click(preview.point)
    assert not any(n == "click" for n, _ in t.calls)


def test_preview_rejects_wrong_window_stale_target_and_invisible_element(rig):
    c, _ = rig
    w = c.window(pid=7, window_id=10)
    old = w.observe()
    new = w.observe()
    other = c.window(pid=7, window_id=11).observe()
    for target, code in [(old.point(1, 1), "stale_observation"),
                         (other.point(1, 1), "target_mismatch"),
                         (new.find("Offscreen"), "outside_window")]:
        with pytest.raises(ComputerError) as exc:
            new.preview(target)
        assert exc.value.code == code
    with pytest.raises(ComputerError):
        new.preview(replace(new.point(1, 1), x=float("nan")))
    with pytest.raises(ComputerError, match="screenshot"):
        w.observe(screenshot=False).preview(new.point(1, 1))


@pytest.mark.parametrize("options", [{"radius": 0}, {"radius": 513}, {"radius": 2.5},
                                    {"scale": float("nan")}, {"scale": 9}])
def test_preview_rejects_invalid_detail_options(rig, options):
    c, _ = rig
    s = c.window(pid=7, window_id=10).observe()
    with pytest.raises(ComputerError):
        s.preview(s.point(10, 10), **options)


def test_mcp_preview_returns_two_images_without_transport_or_invalidating_snapshot(rig):
    c, t = rig
    service = ToolService(c)
    s = call(service, "tobkiri_observe", pid=7, window_id=10)["structuredContent"]
    args = dict(pid=7, window_id=10, observation_id=s["observation_id"])
    before = list(t.calls)
    r = call(service, "tobkiri_preview", **args, point=[180, 120])
    assert not r.get("isError") and t.calls == before
    assert [b["type"] for b in r["content"]] == ["text", "image", "image"]
    assert r["structuredContent"]["point"] == [180, 120]
    assert r["structuredContent"]["input_sent"] is False
    assert c._latest[(7, 10)] == s["observation_id"]
    assert not call(service, "tobkiri_act", **args, point=[180, 120], action="click").get("isError")
    assert call(service, "tobkiri_preview", **args, point=[180, 120])["isError"]


def test_mcp_preview_uses_zoom_and_rejects_cross_window_zoom(rig):
    c, t = rig
    service = ToolService(c)
    s = call(service, "tobkiri_observe", pid=7, window_id=10)["structuredContent"]
    args = dict(pid=7, window_id=10, observation_id=s["observation_id"])
    z = call(service, "tobkiri_zoom", **args, region=[100, 100, 200, 200], scale=2)["structuredContent"]
    before = list(t.calls)
    r = call(service, "tobkiri_preview", **args, zoom_id=z["zoom_id"], point=[40, 60])
    assert r["structuredContent"]["point"] == [120, 130] and t.calls == before
    other = call(service, "tobkiri_observe", pid=7, window_id=11)["structuredContent"]
    before = list(t.calls)
    r = call(service, "tobkiri_preview", pid=7, window_id=11, observation_id=other["observation_id"],
             zoom_id=z["zoom_id"], point=[40, 60])
    assert r["structuredContent"]["error"]["code"] == "stale_zoom" and t.calls == before


def test_mcp_bad_preview_never_creates_session_or_sends_input(rig):
    c, t = rig
    service = ToolService(c)
    before = list(t.calls)
    r = call(service, "tobkiri_preview", pid=7, window_id=10, observation_id="unknown", point=[2, 3])
    assert r["isError"] and t.calls == before
    s = call(service, "tobkiri_observe", pid=7, window_id=10)["structuredContent"]
    before = list(t.calls)
    for target in ({}, {"point": [1, 1], "element_id": 1}, {"zoom_id": "x", "element_id": 1},
                   {"point": [900, 600]}, {"element_id": 3}):
        r = call(service, "tobkiri_preview", pid=7, window_id=10, observation_id=s["observation_id"], **target)
        assert r["isError"] and t.calls == before
