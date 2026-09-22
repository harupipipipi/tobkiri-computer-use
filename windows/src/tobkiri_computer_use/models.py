from __future__ import annotations

import base64
import copy
from dataclasses import dataclass, field
from io import BytesIO
import math
from numbers import Integral
from pathlib import Path
import uuid

from PIL import Image, ImageDraw
from .geometry import Frame, Crop
from .transport import ComputerError
from .version import VERSION


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    observation_id: str
    surface: tuple[int, int]


@dataclass(frozen=True)
class Element:
    id: int
    role: str
    label: str
    value: object
    token: str | None
    observation_id: str
    surface: tuple[int, int]
    point: Point | None
    raw: dict = field(repr=False)

    def to_dict(self):
        result = {"id": self.id, "role": self.role, "label": self.label}
        for key in ("value", "enabled", "selected", "actions"):
            if key in self.raw:
                result[key] = self.raw[key]
        if self.point:
            result["center"] = [round(self.point.x, 2), round(self.point.y, 2)]
        return result


@dataclass
class Observation:
    id: str
    surface: tuple[int, int]
    driver_snapshot_id: str
    frame: Frame | None
    elements: tuple[Element, ...]
    tree: str
    image: bytes | None
    raw: dict = field(repr=False)
    changes: str = ""
    marks: tuple[dict, ...] = ()
    cursor: dict | None = None

    def find_all(self, label=None, *, role=None, contains=False):
        def match(e):
            return (role is None or e.role == role) and (label is None or (
                str(label).casefold() in e.label.casefold() if contains
                else str(label).casefold() == e.label.casefold()))
        return [e for e in self.elements if match(e)]

    def _missing_element_details(self, label, role, contains):
        reason = self.raw.get("degraded_reason")
        ax_window_unresolved = isinstance(reason, str) and reason.startswith("ax_window_unresolved")
        ax_application_unresponsive = isinstance(reason, str) and reason.startswith("ax_application_unresponsive")
        screenshot_frame_valid = self.raw.get("screenshot_frame_valid", self.frame is not None)
        pixel_frame_available = bool(self.image and self.frame and screenshot_frame_valid)
        if ax_application_unresponsive:
            next_step = "wait_for_application_then_fresh_observation"
            pixel_path = "background_pixel_unavailable_app_unresponsive"
        elif ax_window_unresolved:
            next_step = "fresh_observation_before_pixel"
            pixel_path = "background_pixel_unavailable_ax_window_unresolved"
        elif pixel_frame_available:
            next_step = "current_bound_pixel_or_fresh_observation"
            pixel_path = "current_screenshot_bound_point_available"
        else:
            next_step = "fresh_observation_with_screenshot"
            pixel_path = "valid_screenshot_frame_required"
        return {
            "selector": {
                "label": None if label is None else str(label),
                "role": None if role is None else str(role),
                "contains": bool(contains),
            },
            "surface": {"pid": self.surface[0], "window_id": self.surface[1]},
            "observation_id": self.id,
            "returned_element_count": self.raw.get("returned_element_count", len(self.elements)),
            "element_count": self.raw.get("element_count", len(self.elements)),
            "elements_complete": self.raw.get("elements_complete", False),
            "degraded_reason": reason,
            "screenshot_frame_valid": screenshot_frame_valid,
            "pixel_frame_available": pixel_frame_available,
            "background_input": self.raw.get("background_input", {}),
            "escalation": self.raw.get("escalation"),
            "input_sent": False,
            "next_step": next_step,
            "pixel_path": pixel_path,
        }

    def find(self, label=None, *, role=None, contains=False):
        matches = self.find_all(label, role=role, contains=contains)
        if not matches:
            details = self._missing_element_details(label, role, contains)
            if details["pixel_path"] == "current_screenshot_bound_point_available":
                advice = "A current screenshot-bound point is available through the normal window pixel path."
            elif details["pixel_path"] == "background_pixel_unavailable_ax_window_unresolved":
                advice = "The AX window is unresolved, so obtain a fresh observation before choosing an input path."
            elif details["pixel_path"] == "background_pixel_unavailable_app_unresponsive":
                advice = "The application's accessibility server did not respond. Wait for it to respond, then obtain a fresh observation."
            else:
                advice = "Observe again with a valid screenshot frame before using a pixel path."
            raise ComputerError(
                "element_not_found",
                f"Expected one match for {label!r}, got 0. No input was sent. "
                f"This does not prove the control is absent. {advice}",
                details=details,
            )
        if len(matches) != 1:
            raise ComputerError(
                "ambiguous_element",
                f"Expected one match for {label!r}, got {len(matches)}. Refine the label/role and observe.",
                details=[e.to_dict() for e in matches[:20]],
            )
        return matches[0]

    def element(self, element_id):
        for e in self.elements:
            if e.id == element_id:
                return e
        raise ComputerError("element_not_found", f"Element {element_id} is not in observation {self.id}.")

    def point(self, x, y):
        if not self.frame or not self.image:
            raise ComputerError("no_pixel_frame", "Observe with screenshot=True before pixel actions.")
        self.frame.check_pixel(x, y)
        return Point(x, y, self.id, self.surface)

    def grid(self, region, *, rows, columns):
        """Return rows of snapshot-bound points at evenly spaced cell centers.

        Region is [left, top, right, bottom] in this screenshot's pixels, selected
        from the observed image. This performs no detection, input or live read.
        Like point(), these points expire after a new observation or input; use
        timeline() for a pre-observed series on a known static grid.
        """
        if not self.frame or not self.image:
            raise ComputerError("no_pixel_frame", "Observe with screenshot=True before making a grid.")
        if (any(isinstance(v, bool) or not isinstance(v, Integral) or v < 1 for v in (rows, columns))
                or rows * columns > 2000):
            raise ComputerError("invalid_grid", "Use positive integer rows/columns and at most 2000 cells.")
        try:
            bounds = tuple(region)
            valid = len(bounds) == 4 and all(not isinstance(v, bool) and math.isfinite(v) for v in bounds)
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise ComputerError("invalid_grid", "Use four finite screenshot coordinates: [left, top, right, bottom].")
        left, top, right, bottom = map(float, bounds)
        if not (0 <= left < right <= self.frame.pixel_width and 0 <= top < bottom <= self.frame.pixel_height):
            raise ComputerError("out_of_bounds", "Grid region must lie wholly inside this screenshot and have positive area.")
        return tuple(tuple(self.point(left + (column + .5) * (right - left) / columns,
                                      top + (row + .5) * (bottom - top) / rows)
                           for column in range(columns)) for row in range(rows))

    def png(self, *, marks=True, labels=False):
        if not self.image:
            raise ComputerError("no_screenshot", "This observation has no screenshot.")
        im = Image.open(BytesIO(self.image)).convert("RGB")
        draw = ImageDraw.Draw(im)
        if marks:
            for mark in self.marks:
                x, y = mark["x"], mark["y"]
                draw.ellipse((x-7, y-7, x+7, y+7), fill="#ef3340", outline="white", width=2)
                draw.text((x+10, y-8), str(mark["sequence"]), fill="#ef3340", stroke_width=1, stroke_fill="white")
        if labels:
            for e in self.elements:
                if e.point and e.role not in ("AXWindow", "window"):
                    x, y = e.point.x, e.point.y
                    draw.rectangle((x-3, y-3, x+25, y+14), fill="#164bc5")
                    draw.text((x, y), str(e.id), fill="white")
        out = BytesIO()
        im.save(out, format="PNG")
        return out.getvalue()

    def save(self, path, *, marks=True, labels=False):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.png(marks=marks, labels=labels))
        return str(path.resolve())

    def zoom(self, region, *, scale=3.0, max_dimension=1600):
        if not self.image or not self.frame:
            raise ComputerError("no_screenshot", "Observe with a screenshot before zooming.")
        if len(region) != 4 or not all(math.isfinite(v) for v in region) or not math.isfinite(scale) or not 0 < scale <= 8:
            raise ComputerError("invalid_zoom", "Use [left,top,right,bottom] and 0 < scale <= 8.")
        if not 1 <= max_dimension <= 4096:
            raise ComputerError("invalid_zoom", "max_dimension must be 1..4096.")
        x1, y1, x2, y2 = region
        if x2 <= x1 or y2 <= y1:
            raise ComputerError("invalid_zoom", "Zoom region has no area.")
        left, top = max(0, math.floor(x1)), max(0, math.floor(y1))
        right, bottom = min(self.frame.pixel_width, math.ceil(x2)), min(self.frame.pixel_height, math.ceil(y2))
        if right <= left or bottom <= top:
            raise ComputerError("invalid_zoom", "Zoom region does not intersect the screenshot.")
        width, height = right-left, bottom-top
        ratio = min(scale, max_dimension / max(width, height))
        out_w, out_h = max(1, round(width*ratio)), max(1, round(height*ratio))
        im = Image.open(BytesIO(self.png())).crop((left, top, right, bottom)).resize((out_w, out_h), Image.Resampling.LANCZOS)
        output = BytesIO(); im.save(output, format="PNG")
        return Zoom("z_" + uuid.uuid4().hex, self, Crop(left, top, width, height, out_w, out_h), output.getvalue())

    def preview(self, target: Point | Element, *, radius=60, scale=3):
        """Show a planned click on this saved screenshot without sending input.

        Returns the full marked screenshot plus a detail crop. This does not
        predict application effects or check whether the live layout changed.
        """
        from .preview import preview_click
        return preview_click(self, target, radius=radius, scale=scale)

    def to_dict(self, *, diff=False):
        background_input = self.raw.get("background_input", {})
        routes = background_input.get("routes") if isinstance(background_input, dict) else None
        route = next((r for r in routes or []
                      if isinstance(r, dict) and r.get("route") == "pid_keyboard"), {})
        return {
            "runtime_version": VERSION,
            "observation_id": self.id, "pid": self.surface[0], "window_id": self.surface[1],
            "coordinate_space": "window_screenshot_pixels", "title": self.raw.get("window_title", ""),
            "image_size": [self.frame.pixel_width, self.frame.pixel_height] if self.frame else None,
            "elements": [e.to_dict() for e in self.elements],
            "tree": self.changes if diff else self.tree, "tree_is_diff": diff,
            "elements_complete": self.raw.get("elements_complete", False),
            "degraded_reason": self.raw.get("degraded_reason"),
            "ax_read_errors": copy.deepcopy(self.raw.get("ax_read_errors")),
            "screenshot_frame_valid": self.raw.get("screenshot_frame_valid"),
            "click_history": list(self.marks),
            "cursor": self.cursor,
            "input": {"default_delivery": "background", "background_keyboard": route.get("status", "unknown"),
                      # These are the driver's observation-time facts. Every native action
                      # revalidates them; this helper does not infer a route or its outcome.
                      "exact_window": copy.deepcopy(background_input.get("exact_window"))
                      if isinstance(background_input, dict) else None,
                      "routes": copy.deepcopy(routes),
                      "ax_read_errors": copy.deepcopy(background_input.get("ax_read_errors"))
                      if isinstance(background_input, dict) else None,
                      "native_field_replacement": "set_value (no keyboard focus required)",
                      "foreground": "requires user approval for each action"},
        }

    def image_content(self, *, labels=False):
        return {"type": "image", "mimeType": "image/png", "data": base64.b64encode(self.png(labels=labels)).decode()}


@dataclass
class Zoom:
    id: str
    observation: Observation
    crop: Crop
    image: bytes

    def point(self, x, y):
        return self.observation.point(*self.crop.to_image(x, y))

    def preview(self, x, y, *, radius=60, scale=3):
        """Map this crop's pixels back to the original screenshot and preview."""
        result = self.observation.preview(self.point(x, y), radius=radius, scale=scale)
        result.metadata["source"] = {"zoom_id": self.id, "coordinate_space": "zoom_pixels", "point": [x, y]}
        return result

    def save(self, path):
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.image)
        return str(path.resolve())
