from io import BytesIO

from PIL import Image

from tobkiri_computer_use.computer import (
    _crop_black_padding,
    _normalize_windows_element_frame,
    _normalize_windows_capture,
)


def png(width, height, content_width, content_height, outside=(0, 0, 0)):
    image = Image.new("RGB", (width, height), outside)
    image.paste((240, 240, 240), (0, 0, content_width, content_height))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_crops_only_black_dpi_allocation_padding():
    result, size, changed = _crop_black_padding(png(120, 100, 80, 70), 80, 70)
    assert changed is True
    assert size == (80, 70)
    assert Image.open(BytesIO(result)).size == (80, 70)


def test_crops_narrow_trailing_dwm_black_border():
    result, size, changed = _crop_black_padding(png(120, 100, 78, 68), 80, 70)
    assert changed is True
    assert size == (78, 68)
    assert Image.open(BytesIO(result)).size == (78, 68)


def test_nonblack_discard_region_is_never_cropped():
    original = png(120, 100, 80, 70, outside=(10, 0, 0))
    result, size, changed = _crop_black_padding(original, 80, 70)
    assert changed is False
    assert size == (120, 100)
    assert result == original


def test_dpi_aware_app_keeps_full_image_but_maps_live_frame(monkeypatch):
    import tobkiri_computer_use.computer as module
    monkeypatch.setattr(module.sys, "platform", "win32")
    bounds = {"x": 20, "y": 30, "width": 800, "height": 600}
    monkeypatch.setattr(module, "_win32_window_bounds", lambda hwnd: bounds)
    original = png(1200, 900, 1200, 900)
    result, metadata = _normalize_windows_capture(
        original, {"x": 30, "y": 45, "width": 1200, "height": 900}, 42)
    assert result == original
    assert metadata["reason"] == "win32_dpi_frame_mapping"
    assert metadata["coordinate_image_size"] == [1200, 900]
    assert metadata["win32_window_bounds"] == bounds


def test_uia_frame_is_mapped_from_driver_dpi_space_to_win32_pixels():
    frame = _normalize_windows_element_frame(
        {"x": 300, "y": 250, "w": 150, "h": 60},
        {"x": 100, "y": 100, "width": 900, "height": 750},
        {"x": 50, "y": 50, "width": 600, "height": 500},
    )
    assert frame == {"x": 183.33333333333331, "y": 150.0, "w": 100.0, "h": 40.0}


def test_normalized_capture_coordinates_expand_to_driver_space(rig):
    computer, _ = rig
    window = computer.window(pid=7, window_id=10)
    state = window.observe()
    state.raw["capture_normalization"] = {
        "driver_image_size": [1200, 900],
        "normalized_image_size": [800, 600],
    }
    assert window._driver_coordinates(state, 400, 300) == (600, 450)
