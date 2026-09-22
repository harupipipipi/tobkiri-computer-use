"""Explicit screen-point ⇄ screenshot-pixel ⇄ crop-pixel transforms."""
from dataclasses import dataclass
import math
from .transport import ComputerError


def segment_intersects_rect(start, end, rect):
    """Exact slab intersection, including narrow obstacles between sample points."""
    low, high = 0.0, 1.0
    for origin, delta, left, right in (
        (start[0], end[0]-start[0], rect["x"], rect["x"]+rect["width"]),
        (start[1], end[1]-start[1], rect["y"], rect["y"]+rect["height"]),
    ):
        if delta == 0:
            if not left <= origin <= right:
                return False
        else:
            a, b = sorted(((left-origin)/delta, (right-origin)/delta))
            low, high = max(low, a), min(high, b)
            if low > high:
                return False
    return True


@dataclass(frozen=True)
class Frame:
    x: float
    y: float
    width: float
    height: float
    pixel_width: int
    pixel_height: int

    def __post_init__(self):
        values = (self.x, self.y, self.width, self.height, self.pixel_width, self.pixel_height)
        if not all(math.isfinite(v) for v in values) or min(values[2:]) <= 0:
            raise ComputerError("invalid_frame", "Cannot prove the screenshot coordinate transform.")

    def check_pixel(self, x, y):
        if not (math.isfinite(x) and math.isfinite(y) and 0 <= x < self.pixel_width and 0 <= y < self.pixel_height):
            raise ComputerError("out_of_bounds", "Point is outside this image; use its own pixel coordinates.")
        return float(x), float(y)

    def at_bounds(self, bounds):
        try:
            return Frame(*(bounds[k] for k in ("x", "y", "width", "height")), self.pixel_width, self.pixel_height)
        except (KeyError, TypeError, ValueError) as exc:
            raise ComputerError("invalid_frame", "Live window bounds are unavailable.") from exc

    def same_size(self, other):
        return (abs(self.width-other.width) <= .5 and abs(self.height-other.height) <= .5
                and self.pixel_width == other.pixel_width and self.pixel_height == other.pixel_height)

    def to_screen(self, x, y):
        self.check_pixel(x, y)
        return (self.x + x * self.width / self.pixel_width,
                self.y + y * self.height / self.pixel_height)

    def from_screen(self, x, y):
        return ((x - self.x) * self.pixel_width / self.width,
                (y - self.y) * self.pixel_height / self.height)

    def element_center(self, rect):
        # Only the visible intersection is a valid click point; off-window menus
        # and virtualized zero-height rows must not become negative pixel clicks.
        x, y, w, h = (float(rect[k]) for k in ("x", "y", "w", "h"))
        if not all(math.isfinite(v) for v in (x, y, w, h)) or w <= 1 or h <= 1:
            return None
        left, top = max(self.x, x), max(self.y, y)
        right, bottom = min(self.x + self.width, x + w), min(self.y + self.height, y + h)
        if right <= left or bottom <= top:
            return None
        return self.from_screen((left + right) / 2, (top + bottom) / 2)


@dataclass(frozen=True)
class Crop:
    left: int
    top: int
    width: int
    height: int
    output_width: int
    output_height: int

    def to_image(self, x, y):
        if not (math.isfinite(x) and math.isfinite(y) and 0 <= x < self.output_width and 0 <= y < self.output_height):
            raise ComputerError("out_of_bounds", "Point is outside this zoom image.")
        return (self.left + x * self.width / self.output_width,
                self.top + y * self.height / self.output_height)
