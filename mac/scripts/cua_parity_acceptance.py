"""Opt-in native/Python/stdio-MCP parity checks on TobkiriFixture only."""
import json
from pathlib import Path
import re

from tobkiri_computer_use import Computer
from tobkiri_computer_use.reloadable import RUNTIME_TOOL
from tobkiri_computer_use.server import HELPERS
from tobkiri_computer_use.transport import McpTransport, structured
from tobkiri_computer_use.version import VERSION

ROOT = Path(__file__).resolve().parents[1]
report = {"version": VERSION, "scope": "Dedicated TobkiriFixture windows only", "checks": {}}


def count(raw):
    return int(re.search(r"Count: (\d+)", raw["tree_markdown"]).group(1))


with Computer() as c:
    a = c.window(app="TobkiriFixture", title="Tobkiri Fixture A", name="parity-A")
    b = c.window(app="TobkiriFixture", title="Tobkiri Fixture B", name="parity-B")
    report["driver"] = c.transport.server_info
    report["targets"] = [a.target, b.target]
    native = {t["name"]: t for t in c.list_tools()}
    with McpTransport([str(ROOT / ".venv/bin/tobkiri-computer-use"), "--surface", "all"]) as mcp:
        assert mcp.server_info["version"] == VERSION
        advertised = {t["name"]: t for t in mcp.list_tools()}
        assert all(advertised[name] == schema for name, schema in native.items())
        expected_helpers = {tool["name"] for tool in HELPERS} | {RUNTIME_TOOL["name"]}
        assert set(advertised) == set(native) | expected_helpers
        report["native_tool_count"] = len(native)
        report["checks"]["every_native_descriptor_preserved"] = True
        index = structured(mcp.call("tobkiri_tools"))
        assert index["runtime_version"] == VERSION

        state = a.observe()
        before = count(state.raw)
        # Read-only discovery must not force models to capture again.
        c.tool("list_windows", {"pid": a.surface[0]})
        r = a.click(state.find("Increment"))
        assert count(r.observation.raw) == before + 1
        report["checks"]["metadata_read_preserves_helper_input"] = True

        state = a.observe()
        # Refreshing B's native cache must not invalidate A's helper handle.
        c.tool("get_window_state", {"pid": b.surface[0], "window_id": b.surface[1],
                                   "session": b.session, "include_screenshot": False})
        r = a.click(state.find("Increment"))
        assert count(r.observation.raw) == count(state.raw) + 1
        report["checks"]["other_window_snapshot_preserves_helper_input"] = True

        args = {"pid": a.surface[0], "window_id": a.surface[1], "session": a.session}
        state = a.observe()
        button = state.find("Increment")
        result = structured(c.transport.call("click", {**args, "element_token": button.token}))
        assert result.get("effect") != "refused"
        after = a.observe()
        assert count(after.raw) == count(state.raw) + 1
        report["checks"]["direct_cua_semantic_click"] = True

        # The registered native tool is available without a Tobkiri wrapper call.
        capture = {"pid": a.surface[0], "window_id": a.surface[1], "include_screenshot": True}
        raw = structured(mcp.call("get_window_state", capture))
        token = next(e["element_token"] for e in raw["elements"] if e.get("label") == "Increment")
        result = structured(mcp.call("click", {"pid": a.surface[0], "window_id": a.surface[1],
                                              "element_token": token}))
        assert result.get("effect") != "refused"
        after = structured(mcp.call("get_window_state", capture))
        assert count(after) == count(raw) + 1
        report["checks"]["native_click_through_stdio_mcp"] = True

        # Exercise the coordinate transform that browser pages also use when AX
        # does not expose a button. Every route must hit exactly one same button.
        state = a.observe()
        p = state.find("Increment").point
        c.transport.call("click", {"target": a.target, "x": p.x, "y": p.y, "session": a.session})
        after = a.observe()
        assert count(after.raw) == count(state.raw) + 1
        result = a.click(after.find("Increment").point)
        assert count(result.observation.raw) == count(after.raw) + 1
        report["checks"]["direct_and_helper_pixel_clicks_match"] = True
        result.observation.save(ROOT / "artifacts/cua-parity-result.png")

out = ROOT / "artifacts/cua-parity.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False, indent=2))
