"""Local click-location previews. No transport, cursor, or application input."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from .models import Element, Observation, Point
from .transport import ComputerError


BLUE = "#0078d4"


def _png(image):
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _annotate(image, x, y, caption):
    image = image.convert("RGB")
    draw = ImageDraw.Draw(image)
    # The ring and crosshair surround the exact point; the center stays visible.
    for width, color in ((5, "white"), (3, BLUE)):
        draw.ellipse((x-10, y-10, x+10, y+10), outline=color, width=width)
        for line in ((x-20, y, x-5, y), (x+5, y, x+20, y),
                     (x, y-20, x, y-5), (x, y+5, x, y+20)):
            draw.line(line, fill=color, width=width)
    # Keep labels inside the screenshot even at its bottom/right edge.
    box = draw.textbbox((0, 0), caption)
    width, height = box[2]-box[0]+12, box[3]-box[1]+10
    if width <= image.width and height <= image.height:
        left = x+24 if x+24+width <= image.width else x-24-width
        top = y+24 if y+24+height <= image.height else y-24-height
        left, top = max(0, left), max(0, top)
        draw.rectangle((left, top, left+width, top+height), fill=BLUE)
        draw.text((left+6-box[0], top+5-box[1]), caption, fill="white")
    return _png(image)


@dataclass(frozen=True)
class ClickPreview:
    point: Point
    image: bytes
    detail_image: bytes
    metadata: dict

    def to_dict(self):
        # Do not expose mutable nested metadata held by this preview.
        import copy
        return copy.deepcopy(self.metadata)

    def save(self, path, *, detail=False):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.detail_image if detail else self.image)
        return str(path.resolve())

    def image_contents(self):
        return [{"type": "image", "mimeType": "image/png",
                 "data": base64.b64encode(data).decode()}
                for data in (self.image, self.detail_image)]


def preview_click(observation: Observation, target: Point | Element, *, radius=60, scale=3):
    if not observation.image or not observation.frame:
        raise ComputerError("no_pixel_frame", "A click preview needs an observed screenshot and its pixel frame.")
    if not isinstance(target, (Point, Element)):
        raise ComputerError("invalid_target", "Use an observed Element or observation.point(x, y).")
    if target.surface != observation.surface:
        raise ComputerError("target_mismatch", "Preview target belongs to a different window.")
    if target.observation_id != observation.id:
        raise ComputerError("stale_observation", "Preview target belongs to a different observation.")
    point = target.point if isinstance(target, Element) else target
    if point is None:
        raise ComputerError("outside_window", "This element has no visible screenshot center to preview.")
    if point.observation_id != observation.id or point.surface != observation.surface:
        raise ComputerError("target_mismatch", "Element center belongs to a different observation or window.")
    observation.frame.check_pixel(point.x, point.y)
    if not isinstance(radius, int) or isinstance(radius, bool) or not 8 <= radius <= 512:
        raise ComputerError("invalid_preview", "Detail radius must be an integer from 8 to 512 screenshot pixels.")
    x, y = point.x, point.y
    # Crop the unmodified observation before drawing either preview marker.
    zoom = observation.zoom([x-radius, y-radius, x+radius, y+radius], scale=scale)
    detail_x = (x-zoom.crop.left)*zoom.crop.output_width/zoom.crop.width
    detail_y = (y-zoom.crop.top)*zoom.crop.output_height/zoom.crop.height
    caption = f"PREVIEW ({x:g}, {y:g})"
    image = _annotate(Image.open(BytesIO(observation.png())), x, y, caption)
    detail_image = _annotate(Image.open(BytesIO(zoom.image)), detail_x, detail_y, caption)
    metadata = {
        "mode": "preview_only", "input_sent": False, "cursor_moved": False,
        "basis": "saved_observation", "observation_id": observation.id,
        "pid": observation.surface[0], "window_id": observation.surface[1],
        "coordinate_space": "window_screenshot_pixels", "point": [x, y],
        "image_size": [observation.frame.pixel_width, observation.frame.pixel_height],
        "detail": {"region": [zoom.crop.left, zoom.crop.top,
                               zoom.crop.left+zoom.crop.width, zoom.crop.top+zoom.crop.height],
                   "image_size": [zoom.crop.output_width, zoom.crop.output_height],
                   "point": [detail_x, detail_y], "coordinate_space": "detail_image_pixels"},
        "legend": {"blue_crosshair": "planned click location", "red_numbered_dots": "past click attempts"},
        "effect": "not_predicted", "live_target_checked": False, "images_order": ["overview", "detail"],
    }
    if isinstance(target, Element):
        metadata["element"] = target.to_dict()
        metadata["target_kind"] = "element_center"
    else:
        metadata["target_kind"] = "point"
    return ClickPreview(point, image, detail_image, metadata)
