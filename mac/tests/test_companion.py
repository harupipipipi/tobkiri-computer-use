import json
import socket
import sys

import pytest

from tobkiri_computer_use.companion import CompanionPublisher
from tobkiri_computer_use import ComputerError


@pytest.fixture
def receiver(monkeypatch):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.settimeout(.1)
        monkeypatch.setenv("TOBKIRI_COMPANION_PORT", str(listener.getsockname()[1]))
        yield listener


def drain(listener):
    events = []
    while True:
        try:
            events.append(json.loads(listener.recv(4096)))
        except socket.timeout:
            return events


def enable(computer):
    computer._companion.close()
    computer._companion = CompanionPublisher(True)


def test_disabled_by_default_does_not_open_socket(monkeypatch):
    monkeypatch.delenv("TOBKIRI_COMPANION", raising=False)
    pub = CompanionPublisher()
    assert not pub.enabled and pub._socket is None
    pub.anchor("one", (12, 23))
    with pub.action("one", "click", {}):
        pass
    pub.close()


def test_private_text_never_leaves_input_transport(rig, receiver):
    c, transport = rig
    enable(c)
    w = c.window(pid=7, window_id=10)
    w.type_text(w.observe().find("Name"), "PRIVATE-CONTENT-123")
    events = drain(receiver)
    assert any(e["action"] == "type" and e["phase"] == "start" for e in events)
    assert any(e["action"] == "type" and e["phase"] == "end" for e in events)
    assert "PRIVATE-CONTENT" not in json.dumps(events)
    assert "element_token" not in json.dumps(events)
    assert sum(name == "type_text" for name, _ in transport.calls) == 1


def test_geometry_translation_hide_and_close(rig, receiver):
    c, t = rig
    enable(c)
    w = c.window(pid=7, window_id=10)
    state = w.observe()
    w.move(state.point(200, 160))
    initial = drain(receiver)[-1]
    assert initial["point"] == [-700, 180]
    t.bounds["x"] += 111
    c._cursors.tick()
    assert drain(receiver)[-1]["point"] == [-589, 180]
    t.bounds["width"] += 30
    c._cursors.tick()
    assert drain(receiver)[-1]["phase"] == "hide"
    t.bounds["width"] -= 30
    c._cursors.tick()
    assert not drain(receiver)  # A resize may never resurrect a stale anchor.


def test_sessions_are_distinct_and_errors_not_success(rig, receiver):
    c, t = rig
    enable(c)
    a = c.mouse("one", pid=7, window_id=10)
    b = c.mouse("two", pid=7, window_id=11)
    a.observe(); b.observe()
    t.error = "click"
    with pytest.raises(ComputerError):
        a.click("Increment")
    events = drain(receiver)
    assert len({e["session"] for e in events}) == 2
    assert events[-1]["outcome"] == "error"
    assert sum(name == "click" for name, _ in t.calls) == 1
    c.close()
    assert len([e for e in drain(receiver) if e["phase"] == "hide"]) == 2


def test_stale_input_has_no_action_animation(rig, receiver):
    c, t = rig
    enable(c)
    w = c.window(pid=7, window_id=10)
    old = w.observe().point(20, 20)
    w.observe()
    with pytest.raises(ComputerError):
        w.click(old)
    assert not any(e["phase"] == "start" for e in drain(receiver))
    assert not any(n == "click" for n, _ in t.calls)


def test_visual_socket_failure_preserves_unknown_input_result(rig, receiver):
    c, t = rig
    enable(c)
    c._companion._socket.close()
    w = c.window(pid=7, window_id=10)
    result = w.click("Increment")
    assert result.delivery["effect"] == "unverifiable"
    assert c.companion_status()["error"]
    assert sum(n == "click" for n, _ in t.calls) == 1


def test_port_error_is_visual_only(monkeypatch):
    monkeypatch.setenv("TOBKIRI_COMPANION_PORT", "bad")
    pub = CompanionPublisher(True)
    assert pub.status()["error"]
    pub.anchor("x", (0, 0))
    with pub.action("x", "click", {}):
        pass
    pub.close()


def test_character_move_does_not_query_disabled_native_marker(rig, receiver):
    c, transport = rig
    enable(c)
    transport.error = "get_agent_cursor_state"
    w = c.window(pid=7, window_id=10)
    moved = w.move(w.observe().point(200, 160))
    assert moved["reported_position"] is None
    assert moved["position_matches"] is None
    assert moved["follow"]["phase"] == "following"
    assert not any(name == "get_agent_cursor_state" for name, _ in transport.calls)
