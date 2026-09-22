import json
import threading
from copy import deepcopy

import pytest

from tobkiri_computer_use import reloadable as r
from tobkiri_computer_use.transport import ComputerError, structured


NATIVE = {"name": "click", "description": "unchanged", "inputSchema": {"type": "object"}}
HELPER = {"name": "tobkiri_future", "description": "new helper", "inputSchema": {"type": "object"}}


class Worker:
    def __init__(self, version):
        self.server_info = {"name": "tobkiri-computer-use", "version": version}
        self.initialize_result = {"serverInfo": self.server_info, "capabilities": {"tools": {}}}
        self.calls, self.closed = [], False
        self.started, self.release = threading.Event(), threading.Event()
        self.block = False
        self.error = None

    def list_tools(self):
        return deepcopy([NATIVE, HELPER])

    def request(self, method, params):
        self.calls.append((method, params))
        if self.block:
            self.started.set()
            assert self.release.wait(3)
        if self.error:
            raise self.error
        if params.get("name") == "tobkiri_tools":
            return r.result({"runtime_version": self.server_info["version"], "tools": [{"name": "click"}]})
        return {"content": [{"type": "text", "text": "native result"}], "isError": False}

    def close(self):
        self.closed = True


@pytest.fixture
def proxy(tmp_path, monkeypatch):
    monkeypatch.setattr(r, "source_digest", lambda: "valid")
    workers, notifications, commands = [], [], []
    def factory(command):
        commands.append(command)
        worker = Worker(str(len(workers) + 1))
        workers.append(worker)
        return worker
    service = r.ReloadableServer(["fixed-python", "--approval", "macos-dialog"], factory=factory,
                                 marker=tmp_path / "reload.json", notify=notifications.append)
    yield service, workers, notifications, commands
    service.close()


def call(service, tool_name, **arguments):
    return service.request("tools/call", {"name": tool_name, "arguments": arguments})


def update(service, digest="valid", revision="next"):
    service.marker.write_text(json.dumps({"revision": revision, "digest": digest}))


def test_original_tools_results_and_startup_policy_are_preserved(proxy):
    service, workers, notes, commands = proxy
    assert NATIVE in service.request("tools/list")["tools"]
    assert service.request("initialize")["capabilities"]["tools"]["listChanged"] is True
    assert call(service, "click", x=1) == {"content": [{"type": "text", "text": "native result"}], "isError": False}
    before = service.worker
    status = structured(call(service, "tobkiri_runtime", action="reload"))
    assert status["generation"] == 2 and before.closed
    assert commands[0] == commands[1] == ["fixed-python", "--approval", "macos-dialog"]
    assert notes[0]["method"] == "notifications/tools/list_changed"


def test_publish_reloads_at_next_boundary_and_drops_pending_stale_input(proxy):
    service, workers, _, _ = proxy
    update(service)
    response = call(service, "click", element_token="old")
    assert response["isError"] and structured(response)["error"]["code"] == "runtime_reloaded"
    assert all(not w.calls for w in workers)
    assert workers[0].closed and not workers[1].closed
    call(service, "get_window_state", window_id=10)
    assert len(workers) == 2 and len(workers[1].calls) == 1


def test_published_update_allows_a_fresh_observation(proxy):
    service, workers, _, _ = proxy
    update(service)
    call(service, "tobkiri_observe", pid=7, window_id=10)
    assert workers[1].calls[0][1]["name"] == "tobkiri_observe"


def test_reload_does_not_interrupt_an_inflight_action(proxy):
    service, workers, _, _ = proxy
    old = workers[0]
    old.block = True
    action = threading.Thread(target=lambda: call(service, "click", x=1))
    action.start()
    assert old.started.wait(1)
    update(service)
    reload_done = threading.Event()
    reload = threading.Thread(target=lambda: (call(service, "tobkiri_runtime", action="status"), reload_done.set()))
    reload.start()
    assert not reload_done.wait(.05) and not old.closed
    old.release.set()
    action.join(3); reload.join(3)
    assert reload_done.is_set() and old.closed
    assert len(old.calls) == 1 and not workers[1].calls


def test_invalid_or_partially_written_update_retains_old_worker_and_sends_nothing(proxy):
    service, workers, _, _ = proxy
    update(service, digest="unfinished")
    with pytest.raises(ComputerError, match="Old worker retained"):
        call(service, "click", x=1)
    assert len(workers) == 1 and not workers[0].closed and not workers[0].calls


def test_candidate_startup_failure_retains_old_worker(proxy):
    service, workers, _, _ = proxy
    def fail(command):
        raise RuntimeError("worker won't boot")
    service.factory = fail
    with pytest.raises(ComputerError, match="Old worker retained"):
        call(service, "tobkiri_runtime", action="reload")
    assert service.worker is workers[0] and not workers[0].closed


def test_explicit_reload_can_accept_installed_changes_without_publishing(proxy):
    service, workers, _, _ = proxy
    update(service, digest="previous-published-build")
    service.revision = r.read_marker(service.marker)
    status = structured(call(service, "tobkiri_runtime", action="reload"))
    assert status["generation"] == 2 and workers[0].closed
    assert structured(call(service, "tobkiri_runtime"))["generation"] == 2


def test_timeout_is_not_replayed_or_reloaded(proxy):
    service, workers, _, _ = proxy
    workers[0].error = ComputerError("timeout", "input may have landed")
    with pytest.raises(ComputerError):
        call(service, "click", x=1)
    with pytest.raises(ComputerError, match="uncertain"):
        call(service, "tobkiri_runtime", action="reload")
    status = structured(call(service, "tobkiri_runtime", action="status"))
    assert status["worker_outcome_unknown"] and len(workers) == 1 and len(workers[0].calls) == 1


def test_new_helpers_can_be_discovered_and_called_through_existing_tools(proxy):
    service, workers, _, _ = proxy
    assert structured(call(service, "tobkiri_tools", name="tobkiri_future")) == HELPER
    index = structured(call(service, "tobkiri_tools"))
    assert {t["name"] for t in index["helpers"]} == {"tobkiri_future", "tobkiri_runtime"}
    call(service, "tobkiri_call", name="tobkiri_future", arguments={"a": 1})
    assert workers[0].calls[-1][1] == {"name": "tobkiri_future", "arguments": {"a": 1}}
    assert structured(call(service, "tobkiri_call", name="tobkiri_runtime", arguments={"action": "status"}))["generation"] == 1


def test_runtime_rejects_untrusted_command_or_permission_override(proxy):
    service, workers, _, _ = proxy
    for args in ({"action": "reload", "command": "anything"}, {"action": "reload", "approval": "allow"}):
        assert call(service, "tobkiri_runtime", **args)["isError"]
    assert len(workers) == 1


def test_publish_is_explicit_and_atomic(tmp_path, monkeypatch):
    monkeypatch.setattr(r, "source_digest", lambda: "built")
    marker = tmp_path / "reload.json"
    first = r.publish(marker)
    assert r.read_marker(marker) == first
    second = r.publish(marker)
    assert second["revision"] != first["revision"] and second["digest"] == "built"
    assert not list(tmp_path.glob("*.tmp"))


def test_source_digest_checks_syntax_without_executing(tmp_path):
    code = tmp_path / "module.py"
    code.write_text("raise RuntimeError('must not execute')\n")
    before = r.source_digest(tmp_path)
    code.write_text("answer = 42\n")
    assert r.source_digest(tmp_path) != before
    code.write_text("def broken(\n")
    with pytest.raises(SyntaxError):
        r.source_digest(tmp_path)
