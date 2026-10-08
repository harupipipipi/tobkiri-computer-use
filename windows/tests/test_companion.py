import json
import socket
import sys
import threading

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


def test_character_replaces_native_marker_and_uses_physical_anchor(rig, receiver, monkeypatch):
    c, transport = rig
    enable(c)
    monkeypatch.setattr("tobkiri_computer_use.companion.physical_point",
                        lambda point, hwnd: (point[0] * 1.5, point[1] * 1.5))
    w = c.window(pid=7, window_id=10)
    transport.error = "get_agent_cursor_state"
    moved = w.move(w.observe().point(200, 160))
    assert moved["reported_position"] is None
    assert moved["position_matches"] is None
    assert moved["follow"]["phase"] == "following"
    assert drain(receiver)[-1]["point"] == [-1050, 270]
    assert not any(name == "set_agent_cursor_enabled" and args["enabled"]
                   for name, args in transport.calls)


@pytest.mark.parametrize("delayed_icmp", [False, True])
def test_input_waits_for_matching_renderer_arrival(receiver, delayed_icmp):
    pub = CompanionPublisher(True)
    pub.anchor("one", (12, 23))
    receiver.recvfrom(4096)  # initial anchor
    if delayed_icmp:
        real_socket = pub._socket
        class DelayedIcmp:
            pending = True
            def __getattr__(self, name):
                return getattr(real_socket, name)
            def recvfrom(self, size):
                if self.pending:
                    self.pending = False
                    raise ConnectionResetError(10054, "old port-unreachable")
                return real_socket.recvfrom(size)
        pub._socket = DelayedIcmp()
    phases = []
    def renderer():
        event, address = receiver.recvfrom(4096)
        event = json.loads(event)
        phases.append(event["phase"])
        receiver.sendto(b"[]", address)
        receiver.sendto(b"not-json", address)
        receiver.sendto(json.dumps({"source":event["source"],"seq":event["seq"],"phase":"accepted"}).encode(),address)
        phases.append("arrived")
        receiver.sendto(json.dumps({"source":event["source"],"seq":event["seq"],"phase":"ready"}).encode(),address)
    thread = threading.Thread(target=renderer)
    thread.start()
    with pub.action("one", "click", {}):
        phases.append("input")
        assert pub.last_ready
    thread.join()
    assert phases == ["prepare", "arrived", "input"]
    assert [e["phase"] for e in drain(receiver)] == ["start", "end"]
    pub.close()
