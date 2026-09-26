"""No live desktop input. Approval decisions below simulate a trusted host."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError

import pytest

from tobkiri_computer_use import ComputerError, ConsentRequest, ConsentDecision, WindowsDialogConsent
from tobkiri_computer_use.consent import require_consent
from tobkiri_computer_use.server import ToolService, handle_rpc


def allow(request):
    return ConsentDecision(request.id, request.digest, True)


def foreground_click(c):
    return c.window(pid=7, window_id=10).click("Increment", delivery_mode="foreground",
                                            fallback_reason="Background test action did not change the counter")


def test_foreground_denied_by_default_and_reason_is_not_approval(rig):
    c, t = rig
    with pytest.raises(ComputerError) as exc:
        foreground_click(c)
    assert exc.value.code == "approval_required"
    assert exc.value.details["scope"] == "one_action"
    assert not any(n == "click" for n, _ in t.calls)


def test_missing_reason_refused_before_prompt(rig):
    c, t = rig
    c._approval_callback = lambda _: pytest.fail("Must validate before asking")
    with pytest.raises(ComputerError) as exc:
        c.window(pid=7, window_id=10).click("Increment", delivery_mode="foreground")
    assert exc.value.code == "fallback_reason_required"


@pytest.mark.parametrize("decision,code", [
    (lambda r: ConsentDecision(r.id, r.digest, False), "approval_denied"),
    (lambda r: True, "invalid_approval"),
    (lambda r: ConsentDecision("old", r.digest, True), "invalid_approval"),
    (lambda r: ConsentDecision(r.id, "changed", True), "invalid_approval"),
])
def test_denied_forged_and_unbound_decisions_send_no_input(rig, decision, code):
    c, t = rig; c._approval_callback = decision
    with pytest.raises(ComputerError) as exc:
        foreground_click(c)
    assert exc.value.code == code
    assert not any(n == "click" for n, _ in t.calls)


def test_each_action_prompts_and_refreshes_element_token(rig):
    c, t = rig; requests = []
    def consent(r):
        requests.append(r)
        return allow(r)
    c._approval_callback = consent
    result = foreground_click(c)
    foreground_click(c)
    assert len(requests) == 2 and requests[0].id != requests[1].id
    sent = [a for n, a in t.calls if n == "click"]
    assert len(sent) == 2
    assert sent[0]["delivery_mode"] == "foreground"
    reviewed = json.loads(requests[0].details_json)["native_arguments"]
    assert sent[0]["element_token"] != reviewed["element_token"]
    assert sent[0]["window_id"] == reviewed["window_id"] == 10
    assert result.approval["request_id"] == requests[0].id
    # Grant replay cannot approve a new request.
    c._approval_callback = lambda _: allow(requests[0])
    with pytest.raises(ComputerError):
        foreground_click(c)
    assert sum(n == "click" for n, _ in t.calls) == 2


@pytest.mark.parametrize("change", ["bounds", "elements"])
def test_ui_changes_during_approval_abort_before_input(rig, change):
    c, t = rig
    def consent(r):
        if change == "bounds": t.bounds["x"] += 10
        else: t.values[10] = "changed while waiting"
        return allow(r)
    c._approval_callback = consent
    with pytest.raises(ComputerError) as exc:
        foreground_click(c)
    assert exc.value.code == "approval_target_changed"
    assert not any(n == "click" for n, _ in t.calls)


def test_pixel_approval_keeps_downscale_and_exact_window(rig):
    c, t = rig; c._approval_callback = allow
    w = c.window(pid=7, window_id=10); s = w.observe(max_dimension=400)
    w.click(s.point(90, 60), delivery_mode="foreground", fallback_reason="Canvas needs foreground input")
    a = next(a for n, a in t.calls if n == "click")
    assert a["target"]["window_id"] == 10 and (a["x"], a["y"]) == (90, 60)
    reads = [a for n, a in t.calls if n == "get_window_state"]
    assert reads[0]["max_dimension"] == reads[1]["max_dimension"] == 400


@pytest.mark.parametrize("name,args", [
    ("click", {"pid": 7, "window_id": 10, "delivery_mode": "foreground", "x": 10, "y": 10}),
    ("press_key", {"scope": "desktop", "key": "a"}),
    ("hotkey", {"delivery_mode": "foreground", "keys": ["cmd", "a"]}),
    ("bring_to_front", {"pid": 7, "window_id": 10}),
    ("move_cursor", {"scope": "desktop", "x": 10, "y": 10}),
    ("move_cursor", {"target": {"kind": "desktop", "display_id": "primary"}, "x": 10, "y": 10}),
])
def test_raw_foreground_desktop_and_focus_share_consent_gate(rig, name, args):
    c, t = rig
    with pytest.raises(ComputerError) as exc:
        c.tool(name, args)
    assert exc.value.code == "approval_required"
    assert not any(n == name for n, _ in t.calls)
    c._approval_callback = allow
    c.tool(name, args)
    assert sum(n == name for n, _ in t.calls) == 1


@pytest.mark.parametrize("name,args", [
    ("move_cursor", {"target": {"kind": "window", "pid": 7, "window_id": 10}, "x": 10, "y": 10}),
    ("move_cursor", {"scope": "window", "x": 10, "y": 10}),
    ("move_cursor", {"x": 10, "y": 10}),
    ("get_desktop_state", {"scope": "desktop"}),
    ("zoom", {"target": {"kind": "desktop"}}),
])
def test_desktop_observation_and_virtual_overlay_do_not_request_takeover(rig, name, args):
    c, t = rig
    c._approval_callback = lambda _: pytest.fail("No hardware input to approve")
    c.tool(name, args)
    assert any(n == name for n, _ in t.calls)


def test_opaque_trajectory_replay_available_after_takeover_approval(rig):
    c, t = rig
    with pytest.raises(ComputerError) as exc:
        c.tool("replay_trajectory", {"dir": "opaque"})
    assert exc.value.code == "approval_required"
    assert not t.calls
    c._approval_callback = allow
    c.tool("replay_trajectory", {"dir": "opaque"})
    assert t.calls == [("replay_trajectory", {"dir":"opaque"})]


def test_mcp_foreground_requires_real_consent_not_approved_argument(rig):
    c, t = rig; service = ToolService(c, compact=True)
    args = dict(pid=7, window_id=10, action="click", label="Increment", delivery_mode="foreground",
                fallback_reason="Background failed", include_image=False)
    def call(a):
        return handle_rpc(service, {"method": "tools/call", "params": {"name": "tobkiri_act", "arguments": a}})
    assert call(args)["structuredContent"]["error"]["code"] == "approval_required"
    assert call({**args, "approved": True})["structuredContent"]["error"]["code"] == "invalid_arguments"
    assert not any(n == "click" for n, _ in t.calls)
    c._approval_callback = allow
    assert call(args)["structuredContent"]["approval"]["scope"] == "one_action"


def test_callback_failure_and_expiry_fail_closed(monkeypatch):
    r = ConsentRequest.create("click", {"x": 1}, "test")
    with pytest.raises(FrozenInstanceError):
        r.action = "type_text"
    def broken(_): raise OSError("No operator channel")
    with pytest.raises(ComputerError) as exc: require_consent(broken, r)
    assert exc.value.code == "approval_unavailable"
    times = iter([10, 131])
    monkeypatch.setattr("tobkiri_computer_use.consent.time.monotonic", lambda: next(times))
    with pytest.raises(ComputerError) as exc: require_consent(allow, r)
    assert exc.value.code == "approval_expired"


def test_windows_dialog_rejects_other_platforms(monkeypatch):
    r = ConsentRequest.create("click", {}, "test")
    monkeypatch.setattr("tobkiri_computer_use.consent.sys.platform", "linux")
    with pytest.raises(ComputerError) as exc:
        require_consent(WindowsDialogConsent(), r)
    assert exc.value.code == "approval_unavailable"


def test_windows_dialog_refuses_unreviewable_prompt(monkeypatch):
    r = ConsentRequest.create("type_text", {"text": "safe"}, "x" * 9000)
    monkeypatch.setattr("tobkiri_computer_use.consent.sys.platform", "win32")
    with pytest.raises(ComputerError) as exc:
        require_consent(WindowsDialogConsent(), r)
    assert exc.value.code == "approval_unavailable"


def test_foreground_wait_excludes_other_window_background_input(rig):
    c, t = rig
    a = c.window(pid=7, window_id=10); b = c.window(pid=7, window_id=11)
    pending = threading.Event(); release = threading.Event(); started = threading.Event()
    def consent(r):
        pending.set()
        assert release.wait(3)
        return allow(r)
    c._approval_callback = consent
    with ThreadPoolExecutor(2) as pool:
        front = pool.submit(a.click, "Increment", delivery_mode="foreground", fallback_reason="test")
        assert pending.wait(3)
        def background():
            started.set()
            return b.click("Increment")
        back = pool.submit(background)
        assert started.wait(3)
        assert not any(n == "click" for n, _ in t.calls)
        release.set()
        front.result(timeout=3); back.result(timeout=3)
    assert [args["window_id"] for n, args in t.calls if n == "click"] == [10, 11]


def test_background_operations_never_open_a_prompt(rig):
    c, t = rig
    c._approval_callback = lambda _: pytest.fail("Background input must not prompt")
    w = c.window(pid=7, window_id=10)
    w.set_value("Name", "background")
    w.type_text("Name", "text")
    w.press_key("a", target=w.observe().find("Name"))
    w.click("Increment")
    assert all(a.get("delivery_mode", "background") == "background" for _, a in t.calls)


def test_failure_consumes_approval_and_never_retries(rig):
    c, t = rig; requests = []
    def consent(r):
        requests.append(r.id)
        return allow(r)
    c._approval_callback = consent; t.error = "click"
    for _ in range(2):
        with pytest.raises(ComputerError): foreground_click(c)
    assert len(set(requests)) == 2
    assert sum(n == "click" for n, _ in t.calls) == 2


def test_mutating_caller_args_cannot_change_the_approved_key(rig):
    c, t = rig; modifiers = ["shift"]
    def consent(r):
        modifiers.append("cmd")
        return allow(r)
    c._approval_callback = consent
    w = c.window(pid=7, window_id=10)
    w.press_key("a", target=w.observe().find("Name"), modifiers=modifiers,
                delivery_mode="foreground", fallback_reason="test")
    assert next(a for n, a in t.calls if n == "press_key")["modifiers"] == ["shift"]


def test_denial_invalidates_handles_even_when_no_input_was_sent(rig):
    c, t = rig; w = c.window(pid=7, window_id=10); s = w.observe()
    with pytest.raises(ComputerError):
        w.click(s.find("Increment"), delivery_mode="foreground", fallback_reason="test")
    with pytest.raises(ComputerError) as exc: w.click(s.find("Increment"))
    assert exc.value.code == "stale_observation"


@pytest.mark.parametrize("code,expected", [("no", False), ("yes", True)])
def test_terminal_reads_human_channel_not_mcp_stdin(monkeypatch, code, expected):
    from io import StringIO
    from tobkiri_computer_use import TerminalConsent
    r = ConsentRequest.create("click", {}, "test")
    monkeypatch.setattr("tobkiri_computer_use.consent.sys.platform", "linux")
    class Terminal(StringIO):
        def readline(self):
            return ("ALLOW " + r.id[-8:]) if code == "yes" else "yes"
    terminal = Terminal()
    def open_terminal(path, *args, **kwargs):
        assert path == "/dev/tty"
        return terminal
    monkeypatch.setattr("builtins.open", open_terminal)
    monkeypatch.setattr("tobkiri_computer_use.consent.select.select", lambda *args: ([terminal], [], []))
    assert TerminalConsent()(r).approved is expected


def test_pixel_change_with_same_ax_tree_invalidates_approval(rig):
    import base64
    from io import BytesIO
    from PIL import Image
    c, t = rig; w = c.window(pid=7, window_id=10); state = w.observe()
    original_call = t._call
    def changed_image(name, args):
        result = original_call(name, args)
        if name == "get_window_state":
            out = BytesIO(); Image.new("RGB", (800, 600), "black").save(out, format="PNG")
            result["content"][0]["data"] = base64.b64encode(out.getvalue()).decode()
        return result
    def consent(r):
        t._call = changed_image
        return allow(r)
    c._approval_callback = consent
    with pytest.raises(ComputerError) as exc:
        w.click(state.point(50, 50), delivery_mode="foreground", fallback_reason="Canvas needs this")
    assert exc.value.code == "approval_target_changed"
    assert not any(n == "click" for n, _ in t.calls)


@pytest.mark.parametrize("raw_tool", ["click", "tobkiri_call"])
def test_native_mcp_and_raw_helper_cannot_bypass_approval(rig, raw_tool):
    c, t = rig
    t.list_tools = lambda: [{"name": "click", "inputSchema": {"type": "object"}}]
    service = ToolService(c)
    args = dict(pid=7, window_id=10, delivery_mode="foreground", x=10, y=10)
    request_args = {"name": "click", "arguments": args} if raw_tool == "tobkiri_call" else args
    result = handle_rpc(service, {"method": "tools/call", "params": {"name": raw_tool, "arguments": request_args}})
    assert result["structuredContent"]["error"]["code"] == "approval_required"
    assert not any(n == "click" for n, _ in t.calls)


@pytest.mark.parametrize("action", ["type_text", "press_key", "scroll", "drag"])
def test_all_helper_foreground_actions_require_consent(rig, action):
    c, t = rig; w = c.window(pid=7, window_id=10)
    s = w.observe(); kw = dict(delivery_mode="foreground", fallback_reason="Test needs foreground")
    def execute():
        if action == "type_text": return w.type_text(s.find("Name"), "text", **kw)
        if action == "press_key": return w.press_key("a", target=s.find("Name"), **kw)
        if action == "scroll": return w.scroll(s.point(100, 100), "down", **kw)
        return w.drag(s.point(100, 100), s.point(200, 100), **kw)
    with pytest.raises(ComputerError) as exc: execute()
    assert exc.value.code == "approval_required"
    assert not any(n == action for n, _ in t.calls)
    c._approval_callback = allow
    s = w.observe()
    execute()
    assert sum(n == action for n, _ in t.calls) == 1
