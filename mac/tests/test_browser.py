import pytest

from conftest import FakeTransport
from tobkiri_computer_use import Computer, ComputerError
from tobkiri_computer_use.server import ToolService, handle_rpc
from tobkiri_computer_use.transport import structured


class BrowserTransport(FakeTransport):
    def __init__(self):
        super().__init__()
        self.deny = False
        self.active_tab = "user-tab"
        self.browser_sessions = set()
        self.background_clicks = []

    def list_tools(self):
        descriptors = super().list_tools()
        for name in ("get_browser_state", "browser_prepare", "browser_click", "browser_navigate", "browser_type", "browser_pointer", "browser_dialog"):
            required = [] if name in ("get_browser_state", "browser_prepare") else ["target_id", "tab_id"]
            if name == "browser_type": required += ["ref", "text"]
            if name == "browser_navigate": required += ["url"]
            descriptors.append({"name": name, "inputSchema": {"type": "object", "required": required}})
        return descriptors

    def _call(self, name, a):
        if name == "get_browser_state":
            if self.deny:
                return {"structuredContent": {"status": "refused", "refusal": {
                    "code": "browser_consent_required", "detail": {"next_action": "browser_prepare"}}}}
            if "pid" in a:
                self.browser_sessions.add(a["session"])
            elif a["session"] not in self.browser_sessions:
                raise ComputerError("driver_error", "foreign browser session")
            return {"structuredContent": {"target_id": "target-"+a["session"],
                    "tabs": [{"tab_id": "background-tab", "title": "Fixture"}], "active_tab": self.active_tab}}
        if name.startswith("browser_") and name != "browser_prepare":
            if a["session"] not in self.browser_sessions or a["target_id"] != "target-"+a["session"]:
                raise ComputerError("driver_error", "foreign browser target")
            if name == "browser_click": self.background_clicks.append(dict(a))
            return {"structuredContent": {"effect": "unverifiable", "route": "dom"}}
        if name == "browser_prepare":
            if "strategy" not in a:
                return {"structuredContent":{"status":"ok","prepared":True,"action":"already_prepared"}}
            return {"structuredContent": {"status": "refused", "refusal": {"code": "browser_consent_required"}}}
        return super()._call(name, a)


@pytest.fixture
def browser_rig():
    transport = BrowserTransport()
    def unexpected_prompt(request):
        raise AssertionError("Background virtual input must not ask for hardware approval")
    with Computer(transport=transport, cursor_coordinates="screen_points", cursor_follow_interval=None,
                  approval_callback=unexpected_prompt) as c:
        yield c, transport


def rpc(service, **args):
    return handle_rpc(service, {"method": "tools/call", "params": {"name": "tobkiri_browser", "arguments": args}})


def test_python_browser_targets_hidden_tab_without_activation_or_hardware_prompt(browser_rig):
    c, t = browser_rig
    b = c.browser(pid=7, window_id=10)
    binding = structured(b.bind())
    before = t.active_tab
    result = b.call("click", target_id=binding["target_id"], tab_id="background-tab", ref="p1:3", input_route="dom_event")
    assert structured(result)["effect"] == "unverifiable"
    assert t.background_clicks[0]["tab_id"] == "background-tab"
    assert t.active_tab == before
    assert not any(n in ("click", "press_key", "bring_to_front", "move_cursor") for n, _ in t.calls)


@pytest.mark.parametrize("action", ["click", "set_value", "press_key", "drag"])
def test_browser_refusal_does_not_disable_explicit_observed_native_actions(browser_rig, action):
    c, t = browser_rig; t.deny = True
    w = c.window(pid=7, window_id=10)
    b = c.browser(pid=7, window_id=10)
    assert structured(b.bind())["refusal"]["code"] == "browser_consent_required"
    s = w.observe()
    operations = {"click": lambda: w.click(s.find("Increment")),
                  "set_value": lambda: w.set_value(s.find("Name"), "https://example.test/"),
                  "press_key": lambda: w.press_key("return", target=s.find("Name")),
                  "drag": lambda: w.drag(s.point(10,10), s.point(20,20))}
    # The failed bind itself never selects a tab or sends a native action.
    assert not any(n == action for n, _ in t.calls)
    operations[action]()
    assert any(n == action for n, _ in t.calls)
    assert t.active_tab == "user-tab"


def test_raw_native_surface_remains_available_after_browser_refusal(browser_rig):
    c, t = browser_rig; t.deny = True
    c.tool("get_browser_state", {"pid":7, "window_id":10, "session":"raw"})
    s=structured(c.tool("get_window_state", {"pid":7,"window_id":10}))
    c.tool("set_value", {"pid":7, "window_id":10, "element_token":s['elements'][2]['element_token'], "value":"fixture"})
    assert any(n == "set_value" for n, _ in t.calls)
    assert t.active_tab == "user-tab"


def test_mcp_browser_preserves_refusal_and_session_and_requires_explicit_tab(browser_rig):
    c, t = browser_rig; service = ToolService(c, compact=True)
    report = rpc(service, action="bind", pid=7, window_id=10)["structuredContent"]
    target = report["state"]["target_id"]; bid = report["browser_id"]
    error = rpc(service, action="click", browser_id=bid, ref="p1:3")
    assert error["structuredContent"]["error"]["code"] == "browser_tab_required"
    assert not t.background_clicks
    result = rpc(service, action="click", browser_id=bid, target_id=target, tab_id="background-tab", ref="p1:3", input_route="dom_event")
    assert result["structuredContent"]["state"]["effect"] == "unverifiable"
    assert result["structuredContent"]["cursor"]["phase"] == "not_projected"
    assert t.active_tab == "user-tab"
    assert rpc(service, action="close", browser_id=bid)["structuredContent"]["closed"]
    assert rpc(service, action="state", browser_id=bid)["isError"]


def test_native_profile_permission_not_replaced_with_model_approval(browser_rig):
    c, t = browser_rig; t.deny = True; service = ToolService(c)
    bind = rpc(service, action="bind", pid=7, window_id=10)["structuredContent"]
    prepared = rpc(service, action="prepare", browser_id=bind["browser_id"], isolated=False)
    assert prepared["structuredContent"]["state"]["refusal"]["code"] == "browser_consent_required"
    args = next(a for n,a in t.calls if n == "browser_prepare" and "strategy" in a)
    assert args["strategy"] == {"kind":"existing_profile"}
    assert not any(k in args for k in ("grant", "approved", "no_permissions_gate"))


def test_other_window_and_other_browser_session_stay_independent(browser_rig):
    c,t = browser_rig
    a = c.browser(pid=7, window_id=10); a_ids=structured(a.bind())
    assert c.window(pid=7,window_id=11).click("Increment").delivery["effect"] == "unverifiable"
    b = c.browser(pid=7, window_id=11); b.bind()
    with pytest.raises(ComputerError): b.call("click", target_id=a_ids["target_id"], tab_id="background-tab", ref="p1:3")
    assert not t.background_clicks


def test_non_browser_classification_refusal_does_not_lock_native_app(browser_rig):
    c,t = browser_rig
    original = t._call
    def non_browser(name, args):
        if name == "get_browser_state":
            return {"structuredContent": {"status":"refused", "refusal":{"code":"unsupported_app"}}}
        return original(name, args)
    t._call = non_browser
    c.browser(pid=7,window_id=10).bind()
    assert c.window(pid=7,window_id=10).click("Increment").delivery["effect"] == "unverifiable"


def test_prepare_defaults_to_selected_existing_window(browser_rig):
    c,t = browser_rig
    c.browser(pid=7,window_id=10).prepare()
    a = next(a for n,a in t.calls if n == "browser_prepare" and "strategy" in a)
    assert a["pid"] == 7 and a["window_id"] == 10
    assert a["strategy"] == {"kind":"existing_profile"}
    assert "profile" not in a and "allow_launch" not in a


def test_new_isolated_launch_does_not_short_circuit_on_existing_pid(browser_rig):
    c,t = browser_rig
    c.browser(pid=7,window_id=10).prepare(isolated=True,allow_launch=True)
    a = next(a for n,a in t.calls if n == "browser_prepare")
    assert a["profile"] == {"mode":"isolated_new"}
    assert a["allow_launch"] is True
    assert "pid" not in a and "window_id" not in a and "strategy" not in a


def test_browser_settings_setup_cannot_silently_borrow_foreground(browser_rig):
    c,t = browser_rig
    c._approval_callback = None
    original = t._call
    def needs_setup(name, args):
        if name == "browser_prepare" and "strategy" not in args:
            return {"structuredContent":{"status":"refused","refusal":{"code":"browser_requires_setup"}}}
        return original(name,args)
    t._call = needs_setup
    with pytest.raises(ComputerError) as exc:
        c.browser(pid=7,window_id=10).prepare()
    assert exc.value.code == "approval_required"
    assert not any(n == "browser_prepare" and "strategy" in a for n,a in t.calls)


def test_mcp_rebind_after_prepare_preserves_session(browser_rig):
    c,t = browser_rig; service=ToolService(c,compact=True)
    first=rpc(service,action="bind",pid=7,window_id=10)["structuredContent"]
    bid=first["browser_id"]
    rpc(service,action="prepare",browser_id=bid)
    second=rpc(service,action="bind",browser_id=bid)["structuredContent"]
    assert second["browser_id"] == bid
    assert second["state"]["target_id"] == first["state"]["target_id"]
    assert sum(n == "start_session" for n,_ in t.calls)==1
    refused=rpc(service,action="bind",browser_id=bid,pid=7,window_id=11)
    assert refused["structuredContent"]["error"]["code"]=="invalid_target"
