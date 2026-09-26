import math
import pytest
from tobkiri_computer_use.geometry import Frame, Crop
from tobkiri_computer_use.geometry import segment_intersects_rect
from tobkiri_computer_use import ComputerError


@pytest.mark.parametrize("bounds,size,point", [
    ((0,0,400,300),(800,600),(600,400)),
    ((-1920,-200,400,300),(800,600),(200,100)),
    ((90,70,1200,800),(600,400),(300,200)),
    ((200,300,777,555),(1001,715),(999,700)),
])
def test_roundtrip_retina_downscale_negative_display(bounds, size, point):
    frame = Frame(*bounds, *size)
    assert frame.from_screen(*frame.to_screen(*point)) == pytest.approx(point)


@pytest.mark.parametrize("point", [(-1,0),(800,0),(0,600),(math.nan,0),(0,math.inf)])
def test_reject_outside_and_nonfinite(point):
    with pytest.raises(ComputerError):
        Frame(0,0,400,300,800,600).to_screen(*point)


def test_partially_visible_center_and_offscreen():
    f = Frame(-800,100,400,300,800,600)
    assert f.element_center({"x":-830,"y":120,"w":50,"h":40}) == (20,80)
    assert f.element_center({"x":-830,"y":120,"w":20,"h":40}) is None
    assert f.element_center({"x":-800,"y":120,"w":20,"h":1}) is None


def test_crop_uses_actual_output_dimensions():
    crop = Crop(17, 30, 333, 201, 1000, 604)
    assert crop.to_image(500,302) == (183.5,130.5)
    with pytest.raises(ComputerError):
        crop.to_image(1000,0)


def test_drag_detects_narrow_sibling_between_endpoints():
    rect={"x":23.1,"y":40,"width":.1,"height":20}
    assert segment_intersects_rect((0,50),(100,50),rect)
    assert not segment_intersects_rect((0,30),(100,30),rect)
