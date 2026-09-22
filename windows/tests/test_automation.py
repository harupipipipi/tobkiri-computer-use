from __future__ import annotations

import threading

import pytest

from tobkiri_computer_use.automation import Locator, wait_for
from tobkiri_computer_use.models import Element, Observation, Point
from tobkiri_computer_use.transport import ComputerError
import tobkiri_computer_use.automation as automation


SURFACE = (7, 10)


def observation(number, elements=(), **raw):
    oid = f"o{number}"
    rebound = []
    for index, spec in enumerate(elements, 1):
        label, role, enabled = spec
        point = Point(10 + index, 20 + index, oid, SURFACE)
        item_raw = {
            "element_index": index,
            "label": label,
            "role": role,
            "enabled": enabled,
            "element_token": f"token-{number}-{index}",
        }
        rebound.append(
            Element(
                index,
                role,
                label,
                None,
                item_raw["element_token"],
                oid,
                SURFACE,
                point,
                item_raw,
            )
        )
    return Observation(
        oid,
        SURFACE,
        f"snapshot-{number}",
        None,
        tuple(rebound),
        "",
        None,
        {"elements_complete": False, **raw},
    )


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def is_set(self):
        return False

    def wait(self, delay):
        self.now += delay
        return False


class WindowStub:
    surface = SURFACE

    def __init__(self, observations):
        self.observations = iter(observations)
        self.reads = 0
        self.actions = []

    def _observe_current(self):
        self.reads += 1
        return next(self.observations)

    def _action(self, name, element, *args, **kwargs):
        self.actions.append((name, element.token, args, kwargs))
        return name

    def click(self, element, **kwargs):
        return self._action("click", element, **kwargs)

    def set_value(self, element, value, **kwargs):
        return self._action("set_value", element, value, **kwargs)

    def type_text(self, element, text, **kwargs):
        return self._action("type_text", element, text, **kwargs)

    def scroll(self, element, direction, **kwargs):
        return self._action("scroll", element, direction, **kwargs)

    def move(self, element, **kwargs):
        return self._action("move", element, **kwargs)


@pytest.fixture
def clock(monkeypatch):
    value = Clock()
    monkeypatch.setattr(automation, "_monotonic", value.monotonic)
    return value


def test_locator_waits_for_delayed_enabled_element_with_fresh_point(clock):
    window = WindowStub([
        observation(1),
        observation(2, [("Save", "AXButton", False)]),
        observation(3, [("Save", "AXButton", True)]),
    ])
    element = Locator(window, "Save", role="AXButton").wait(
        timeout=1, poll_interval=.25, stop_event=clock
    )
    assert element.token == "token-3-1"
    assert element.point.observation_id == "o3"
    assert window.reads == 3 and not window.actions


def test_wait_for_retries_element_not_found_and_returns_true_observation(clock):
    window = WindowStub([
        observation(1),
        observation(2, [("Ready", "AXStaticText", True)]),
    ])
    result = wait_for(
        window,
        lambda current: current.find("Ready").label == "Ready",
        timeout=1,
        poll_interval=.1,
        stop_event=clock,
    )
    assert result.id == "o2"
    assert window.reads == 2


def test_ambiguous_locator_fails_immediately_without_input(clock):
    window = WindowStub([
        observation(1, [
            ("Save", "AXButton", True),
            ("Save", "AXButton", True),
        ])
    ])
    with pytest.raises(ComputerError) as exc:
        Locator(window, "Save").click(
            timeout=5, poll_interval=.25, stop_event=clock
        )
    assert exc.value.code == "ambiguous_element"
    assert window.reads == 1 and not window.actions


def test_cancel_before_and_after_read_reports_read_evidence(clock):
    cancelled = threading.Event()
    cancelled.set()
    window = WindowStub([observation(1)])
    with pytest.raises(ComputerError) as before:
        wait_for(window, lambda _observation: False, stop_event=cancelled)
    assert before.value.code == "wait_cancelled"
    assert before.value.details["attempts"] == 0
    assert window.reads == 0

    cancelled.clear()

    class CancellingWindow(WindowStub):
        def _observe_current(self):
            result = super()._observe_current()
            cancelled.set()
            return result

    window = CancellingWindow([observation(2)])
    with pytest.raises(ComputerError) as after:
        wait_for(window, lambda _observation: True, stop_event=cancelled)
    assert after.value.code == "wait_cancelled"
    assert after.value.details["attempts"] == 1
    assert after.value.details["last_observation_id"] == "o2"


def test_deadline_has_last_read_evidence_and_timeout_zero_reads_once(clock):
    window = WindowStub([observation(1), observation(2), observation(3)])
    with pytest.raises(ComputerError) as exc:
        wait_for(
            window,
            lambda _observation: False,
            timeout=.5,
            poll_interval=.25,
            stop_event=clock,
        )
    assert exc.value.code == "wait_timeout"
    assert exc.value.details["attempts"] == 2
    assert exc.value.details["last_observation_id"] == "o2"
    assert exc.value.details["input_sent"] is False

    once = WindowStub([observation(4), observation(5)])
    with pytest.raises(ComputerError) as zero:
        wait_for(once, lambda _observation: False, timeout=0)
    assert zero.value.code == "wait_timeout"
    assert once.reads == 1


def test_predicate_requires_real_bool_and_other_errors_propagate():
    window = WindowStub([observation(1)])
    with pytest.raises(TypeError, match="return bool"):
        wait_for(window, lambda _observation: 1, timeout=0)

    window = WindowStub([observation(2)])
    error = ComputerError("ambiguous_element", "ambiguous")

    def fail(_observation):
        raise error

    with pytest.raises(ComputerError) as exc:
        wait_for(window, fail, timeout=1)
    assert exc.value is error


def test_each_action_resolves_a_fresh_token_and_preserves_kwargs():
    window = WindowStub([
        observation(1, [("Run", "AXButton", True)]),
        observation(2, [("Run", "AXButton", True)]),
        observation(3, [("Run", "AXButton", True)]),
        observation(4, [("Run", "AXButton", True)]),
        observation(5, [("Run", "AXButton", True)]),
    ])
    locator = Locator(window, "Run")
    locator.click(expect="count=1", delivery_mode="background")
    locator.set_value("42", expect="value=42")
    locator.type_text("hello", fallback_reason="fixture")
    locator.scroll("down", amount=4, by="pixel")
    locator.move()
    assert [entry[1] for entry in window.actions] == [
        "token-1-1", "token-2-1", "token-3-1", "token-4-1", "token-5-1"
    ]
    assert window.actions[0][3] == {
        "expect": "count=1", "delivery_mode": "background"
    }
    assert window.actions[1][2] == ("42",)
    assert window.actions[3][2] == ("down",)


def test_unknown_input_outcome_is_never_retried():
    class TimeoutWindow(WindowStub):
        def click(self, element, **kwargs):
            self.actions.append(("click", element.token, (), kwargs))
            raise ComputerError("timeout", "input outcome unknown")

    window = TimeoutWindow([
        observation(1, [("Run", "AXButton", True)]),
        observation(2, [("Run", "AXButton", True)]),
    ])
    with pytest.raises(ComputerError) as exc:
        Locator(window, "Run").click(timeout=1)
    assert exc.value.code == "timeout"
    assert window.reads == 1
    assert len(window.actions) == 1


def test_real_window_wrappers_refresh_native_tokens_and_preserve_observe_options(rig):
    computer, transport = rig
    window = computer.window(pid=7, window_id=10)
    initial = window.observe(
        screenshot=False, max_dimension=400, max_elements=1000, full_tree=True
    )
    assert initial.find("Name", role="AXTextField")

    name = window.locator("Name", role="AXTextField")
    increment = window.locator("Increment", role="AXButton")
    name.set_value("Ada")
    observed = window.wait_for(
        lambda current: current.find("Name", role="AXTextField").value == "Ada",
        timeout=0,
    )
    name.set_value("Grace")
    increment.click()
    increment.click(expect=[{"window": {"exists": True}}])

    inputs = [
        (tool, args)
        for tool, args in transport.calls
        if tool in ("set_value", "click")
    ]
    assert [tool for tool, _args in inputs] == [
        "set_value", "set_value", "click", "click"
    ]
    tokens = [args["element_token"] for _tool, args in inputs]
    assert len(tokens) == len(set(tokens))
    assert observed.find("Name").value == "Ada"
    assert any(element.role == "AXMenuBar" for element in observed.elements)
    reads = [
        args for tool, args in transport.calls if tool == "get_window_state"
    ]
    assert reads
    assert all(
        args["include_screenshot"] is False
        and args["max_dimension"] == 400
        and args["max_elements"] == 1000
        for args in reads
    )


def test_real_window_locator_does_not_retry_unknown_input_error(rig):
    computer, transport = rig
    window = computer.window(pid=7, window_id=10)
    transport.error = "click"

    with pytest.raises(ComputerError) as exc:
        window.locator("Increment", role="AXButton").click(timeout=2)

    assert exc.value.code == "driver_error"
    assert sum(tool == "click" for tool, _args in transport.calls) == 1


@pytest.mark.parametrize(
    "kwargs,exception",
    [
        ({"timeout": True}, TypeError),
        ({"timeout": float("inf")}, ValueError),
        ({"poll_interval": 0}, ValueError),
    ],
)
def test_wait_parameter_validation(kwargs, exception):
    with pytest.raises(exception):
        wait_for(WindowStub([observation(1)]), lambda _observation: True, **kwargs)
