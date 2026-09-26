import copy


def window(computer):
    return computer.window(pid=7, window_id=10)


def test_to_dict_preserves_native_exact_window_and_route_reasons_without_mutating_raw(rig, monkeypatch):
    computer, transport = rig
    native_report = {
        "exact_window": {"status": "matched", "pid": 7, "window_id": 10},
        "routes": [
            {"route": "accessibility", "status": "refused", "reason": "element_outside_target_window"},
            {"route": "window_pointer", "status": "unknown", "reason": "capture_revalidation_pending"},
            {"route": "pid_keyboard", "status": "refused", "reason": "same_pid_keyboard_ambiguity"},
        ],
    }
    original_call = transport._call

    def diagnosed_state(name, arguments):
        result = original_call(name, arguments)
        if name == "get_window_state":
            raw = result["structuredContent"]
            raw["background_input"] = copy.deepcopy(native_report)
            raw["screenshot_frame_valid"] = False
        return result

    monkeypatch.setattr(transport, "_call", diagnosed_state)
    state = window(computer).observe()
    observed = state.to_dict()

    assert observed["screenshot_frame_valid"] is False
    assert observed["input"]["background_keyboard"] == "refused"
    assert observed["input"]["exact_window"] == native_report["exact_window"]
    assert observed["input"]["routes"] == native_report["routes"]
    assert observed["input"]["routes"][1]["status"] == "unknown"
    assert observed["input"]["routes"][2]["reason"] == "same_pid_keyboard_ambiguity"

    observed["input"]["exact_window"]["status"] = "altered"
    observed["input"]["routes"][1]["reason"] = "altered"
    assert state.raw["background_input"] == native_report
    assert state.to_dict()["input"]["exact_window"] == native_report["exact_window"]
    assert state.to_dict()["input"]["routes"] == native_report["routes"]


def test_to_dict_keeps_unprovided_native_frame_and_routes_unknown(rig, monkeypatch):
    computer, transport = rig
    original_call = transport._call

    def legacy_state(name, arguments):
        result = original_call(name, arguments)
        if name == "get_window_state":
            raw = result["structuredContent"]
            raw.pop("background_input", None)
            raw.pop("screenshot_frame_valid", None)
        return result

    monkeypatch.setattr(transport, "_call", legacy_state)
    observed = window(computer).observe().to_dict()

    assert observed["screenshot_frame_valid"] is None
    assert observed["input"]["exact_window"] is None
    assert observed["input"]["routes"] is None
    assert observed["input"]["background_keyboard"] == "unknown"
