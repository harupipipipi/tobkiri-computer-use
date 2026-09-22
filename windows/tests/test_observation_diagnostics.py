import pytest

from tobkiri_computer_use import ComputerError


def window(computer):
    return computer.window(pid=7, window_id=10)


def missing_error(observation, label="Undo"):
    with pytest.raises(ComputerError) as exc:
        observation.find(label, role="AXButton", contains=True)
    return exc.value


def test_zero_match_keeps_list_api_and_reports_current_observation_without_input(rig):
    computer, transport = rig
    state = window(computer).observe()
    calls_before_search = list(transport.calls)

    assert state.find_all("Undo", role="AXButton", contains=True) == []
    error = missing_error(state)

    assert error.code == "element_not_found"
    assert "No input was sent." in str(error)
    assert error.details == {
        "selector": {"label": "Undo", "role": "AXButton", "contains": True},
        "surface": {"pid": 7, "window_id": 10},
        "observation_id": state.id,
        "returned_element_count": len(state.elements),
        "element_count": len(state.elements),
        "elements_complete": False,
        "degraded_reason": None,
        "screenshot_frame_valid": True,
        "pixel_frame_available": True,
        "background_input": {"routes": [{"route": "pid_keyboard", "status": "available"}]},
        "escalation": None,
        "input_sent": False,
        "next_step": "current_bound_pixel_or_fresh_observation",
        "pixel_path": "current_screenshot_bound_point_available",
    }
    assert transport.calls == calls_before_search
    assert state.find("Increment").label == "Increment"


def test_ambiguous_find_keeps_existing_candidate_details(rig):
    computer, _ = rig
    state = window(computer).observe()
    expected = [element.to_dict() for element in state.find_all(role="AXButton")[:20]]

    with pytest.raises(ComputerError) as exc:
        state.find(role="AXButton")

    assert exc.value.code == "ambiguous_element"
    assert exc.value.details == expected


def test_unresolved_ax_diagnostic_disables_pixel_suggestion_despite_valid_screenshot(rig, monkeypatch):
    computer, transport = rig
    w = window(computer)
    valid = w.observe()
    valid_error = missing_error(valid)
    original_call = transport._call

    def unresolved_state(name, args):
        result = original_call(name, args)
        if name == "get_window_state":
            raw = result["structuredContent"]
            raw["elements"] = []
            raw["degraded_reason"] = "ax_window_unresolved: selected AX window is not available"
            raw["escalation"] = {"recommended": "foreground"}
        return result

    monkeypatch.setattr(transport, "_call", unresolved_state)
    unresolved = w.observe()
    calls_before_search = list(transport.calls)
    unresolved_error = missing_error(unresolved)

    assert valid.frame is not None and unresolved.frame is not None
    assert valid_error.details["pixel_path"] == "current_screenshot_bound_point_available"
    assert unresolved_error.details["screenshot_frame_valid"] is True
    assert unresolved_error.details["pixel_frame_available"] is True
    assert unresolved_error.details["degraded_reason"].startswith("ax_window_unresolved")
    assert unresolved_error.details["next_step"] == "fresh_observation_before_pixel"
    assert unresolved_error.details["pixel_path"] == "background_pixel_unavailable_ax_window_unresolved"
    assert "fresh observation" in str(unresolved_error)
    assert transport.calls == calls_before_search


def test_unresponsive_app_does_not_suggest_pixels_and_preserves_native_evidence(rig, monkeypatch):
    computer, transport = rig
    original_call = transport._call
    errors = [{"operation": "AXWindows", "code": -25204}]

    def unresponsive_state(name, args):
        result = original_call(name, args)
        if name == "get_window_state":
            raw = result["structuredContent"]
            raw["elements"] = []
            raw["degraded_reason"] = "ax_application_unresponsive: top-level AX query did not complete"
            raw["ax_read_errors"] = errors
            raw["background_input"]["ax_read_errors"] = errors
        return result

    monkeypatch.setattr(transport, "_call", unresponsive_state)
    state = window(computer).observe()
    calls_before_search = list(transport.calls)
    error = missing_error(state)
    assert error.details["pixel_frame_available"] is True
    assert error.details["pixel_path"] == "background_pixel_unavailable_app_unresponsive"
    assert error.details["next_step"] == "wait_for_application_then_fresh_observation"
    assert error.details["input_sent"] is False
    assert transport.calls == calls_before_search

    serialized = state.to_dict()
    assert serialized["ax_read_errors"] == errors
    assert serialized["input"]["ax_read_errors"] == errors
    serialized["ax_read_errors"][0]["code"] = 0
    serialized["input"]["ax_read_errors"][0]["code"] = 1
    assert state.raw["ax_read_errors"][0]["code"] == -25204
