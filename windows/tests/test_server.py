import pytest
from tobkiri_computer_use.server import ToolService,handle_rpc,SKILL_URI
from tobkiri_computer_use.transport import ComputerError


def call(service,tool_name,**args):
    return handle_rpc(service,{"method":"tools/call","params":{"name":tool_name,"arguments":args}})


def test_all_surface_preserves_original_tools_compact_discovers_them(rig):
    c,t=rig; service=ToolService(c)
    assert t.list_tools()[0] in service.list_tools()
    compact=ToolService(c,compact=True)
    assert len(compact.list_tools())==11
    assert call(compact,"tobkiri_tools",name="native_example")["structuredContent"]==t.list_tools()[0]
    raw=call(compact,"tobkiri_call",name="native_example",arguments={"value":"same"})
    assert raw==t.call("native_example",{"value":"same"})


def test_observe_act_stale_ref_and_post_image(rig):
    c,t=rig; service=ToolService(c)
    s=call(service,"tobkiri_observe",pid=7,window_id=10)["structuredContent"]
    args=dict(pid=7,window_id=10,observation_id=s["observation_id"],element_id=1,action="click")
    result=call(service,"tobkiri_act",**args)
    assert result["structuredContent"]["observation"]["tree_is_diff"]
    assert result["content"][1]["type"]=="image"
    error=call(service,"tobkiri_act",**args)
    assert error["isError"]
    assert error["structuredContent"]["error"]["code"]=="stale_observation"


def test_wrong_zoom_does_not_cross_windows(rig):
    c,t=rig; service=ToolService(c)
    a=call(service,"tobkiri_observe",pid=7,window_id=10)["structuredContent"]
    z=call(service,"tobkiri_zoom",pid=7,window_id=10,observation_id=a["observation_id"],region=[0,0,100,100])["structuredContent"]
    b=call(service,"tobkiri_observe",pid=7,window_id=11)["structuredContent"]
    result=call(service,"tobkiri_act",pid=7,window_id=11,observation_id=b["observation_id"],zoom_id=z["zoom_id"],point=[5,5],action="click")
    assert result["isError"]
    assert not any(n=="click" for n,_ in t.calls)


def test_invalid_args_and_ambiguous_addresses_send_no_input(rig):
    c,t=rig; service=ToolService(c)
    for args in ({"action":"set_value","label":"Name"}, {"action":"click","label":"Increment","point":[1,1]},
                 {"action":"click","label":"Increment","extra":"ignored?"}):
        result=call(service,"tobkiri_act",pid=7,window_id=10,**args)
        assert result["isError"]
    assert not any(n in ("click","set_value") for n,_ in t.calls)


def test_skill_is_packaged_resource(rig):
    c,t=rig; service=ToolService(c)
    r=handle_rpc(service,{"method":"resources/read","params":{"uri":SKILL_URI}})
    assert "name: tobkiri-computer-use" in r["contents"][0]["text"]


def test_mcp_label_action_and_verification_keep_observation_options(rig):
    c, t = rig; service = ToolService(c)
    before = call(service, "tobkiri_observe", pid=7, window_id=10,
                  max_dimension=400, max_elements=1000, full_tree=True)["structuredContent"]
    result = call(service, "tobkiri_act", pid=7, window_id=10,
                  action="click", label="Increment")["structuredContent"]
    assert result["observation"]["image_size"] == before["image_size"]
    verified = call(service, "tobkiri_verify", pid=7, window_id=10,
                    expect=[{"window": {"title_contains": "10"}}])["structuredContent"]
    assert verified["observation"]["image_size"] == before["image_size"]
    assert all(a["max_elements"] == 1000 for n, a in t.calls if n == "get_window_state")
