import base64
from io import BytesIO
import threading
import time

from PIL import Image
import pytest
from tobkiri_computer_use import Computer
from tobkiri_computer_use.transport import ComputerError


class FakeTransport:
    server_info = {"name": "fixture", "version": "0.28.2"}

    def __init__(self):
        self.calls = []
        self.counter = 0
        self.positions = {}
        self.bounds = {"x": -800.0, "y": 100.0, "width": 400.0, "height": 300.0}
        self.values = {10: "", 11: ""}
        self.counts = {10: 0, 11: 0}
        self.closed = False
        self.error = None
        self.delay = 0
        self.active = 0
        self.max_active = 0
        self.guard = threading.Lock()
        self.effect = "unverifiable"
        self.sibling_offset = 500
        self.keyboard_status = "available"
        self.visible = True
        self.include_windows = True
        self.image_scale = 1
        self.element_shift = 0
        self.cached_frames = {}
        self.enabled = {}

    def bounds_for(self, wid):
        return {**self.bounds, "x": self.bounds["x"] + (self.sibling_offset if wid == 11 else 0)}

    def list_tools(self):
        return [{"name": "native_example", "description": "Original description",
                 "inputSchema": {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}}]

    def call(self, name, arguments=None):
        a = arguments or {}
        with self.guard:
            self.calls.append((name, a.copy()))
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            return self._call(name, a)
        finally:
            with self.guard:
                self.active -= 1

    def _call(self, name, a):
        if name == self.error:
            raise ComputerError("driver_error", "refused")
        wid = a.get("window_id", a.get("target", {}).get("window_id", 10))
        if name == "list_windows":
            return {"structuredContent": {"windows": [{"pid": 7, "window_id": i, "app_name": "Fixture", "title": str(i), "bounds": self.bounds_for(i), "is_on_screen": self.visible} for i in (10, 11)] if self.include_windows else []}}
        if name == "get_window_state":
            self.counter += 1
            token = f"s{self.counter:08x}"
            out = BytesIO()
            width = round(min(800, a.get("max_dimension", 800))*self.image_scale)
            height = round(width * 0.75)
            Image.new("RGB", (width, height), "white").save(out, format="PNG")
            bounds = self.bounds_for(wid)
            self.cached_frames[wid] = dict(bounds)
            x, y = bounds["x"], bounds["y"]
            elements = [
                {"element_index": 0, "role": "AXWindow", "label": str(wid), "frame": {"x": x, "y": y, "w": 400, "h": 300}},
                {"element_index": 1, "role": "AXButton", "label": "Increment", "frame": {"x": x+40+self.element_shift, "y": y+40, "w": 100, "h": 40}, "enabled": True, "actions": ["AXPress"]},
                {"element_index": 2, "role": "AXTextField", "label": "Name", "frame": {"x": x+50, "y": y+100, "w": 200, "h": 30}, "value": self.values[wid]},
                {"element_index": 3, "role": "AXButton", "label": "Offscreen", "frame": {"x": x, "y": y-500, "w": 40, "h": 40}},
                {"element_index": 4, "role": "AXMenuBar", "label": "Menu"},
                {"element_index": 5, "role": "AXMenuItem", "label": "Recent private document", "parent_index": 4},
            ]
            for e in elements:
                e["element_token"] = f"{token}:{e['element_index']}"
            raw = {"pid": 7, "window_id": wid, "snapshot_id": token, "window_bounds": bounds,
                   "background_input": {"routes": [{"route":"pid_keyboard", "status":self.keyboard_status}]},
                   "screenshot_width": width, "screenshot_height": height, "screenshot_frame_valid": True,
                   "elements": elements, "elements_complete": False, "window_title": str(wid),
                   "tree_markdown": f'- [0] AXWindow "{wid}"\n  - Count: {self.counts[wid]}\n  - Name: {self.values[wid]}\n- [4] AXMenuBar\n  - Recent private document'}
            return {"structuredContent": raw, "content": [{"type": "image", "data": base64.b64encode(out.getvalue()).decode()}] if a.get("include_screenshot", True) else []}
        if name in ("click", "right_click", "double_click"):
            self.counts[wid] += 1
        if name in ("set_value", "type_text"):
            self.values[wid] = a.get("value", a.get("text"))
        if name == "move_cursor":
            if "target" in a and any(k in a for k in ("scope", "pid", "window_id")):
                raise ComputerError("driver_error", "target cannot be combined with legacy scope, pid, or window_id fields")
            self.positions[a.get("session")] = {"x": a["x"], "y": a["y"]}
        if name == "set_agent_cursor_enabled":
            self.enabled[a.get("session")] = a["enabled"]
        if name == "get_agent_cursor_state":
            return {"structuredContent": {"position": self.positions[a.get("session")], "visual_state": {"phase": "idle"}}}
        if name == "verify_state":
            return {"structuredContent": {"status": "unknown", "reason": "fixture_unknown"}}
        if name == "native_example":
            return {"content": [{"type": "text", "text": "native"}], "structuredContent": a}
        return {"structuredContent": {"effect": self.effect, "route": "accessibility"}}

    def close(self):
        self.closed = True


@pytest.fixture
def rig():
    transport = FakeTransport()
    with Computer(transport=transport, cursor_coordinates="screen_points", cursor_follow_interval=None) as computer:
        yield computer, transport
