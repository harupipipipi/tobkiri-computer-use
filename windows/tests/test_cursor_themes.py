import json
from pathlib import Path
import subprocess
from zipfile import ZipFile

import pytest

from conftest import FakeTransport
from tobkiri_computer_use import Computer, ComputerError
from tobkiri_computer_use.cursor_themes import ACTIONS, BUILTIN_THEMES, main, source_entries, write_source
from tobkiri_computer_use.server import ToolService, handle_rpc


class ThemeTransport(FakeTransport):
    def __init__(self):
        super().__init__()
        self.themes = {}
        self.fallback = None

    def _call(self, name, args):
        if name == "set_agent_cursor_theme":
            if args["theme_id"] == "missing.theme":
                raise ComputerError("driver_error", "theme is not installed")
            self.themes[args["session"]] = {"id": args["theme_id"], "version": "1.0.0",
                                            "profile": "cua-driver-actions-v2",
                                            "reduced_motion": args["reduced_motion"], "fallback": None}
            return {"structuredContent": {"session": args["session"], "theme": self.themes[args["session"]]}}
        if name == "get_agent_cursor_state":
            return {"structuredContent": {"session": args["session"],
                    "theme": {**self.themes.get(args["session"], {"id": "cua.default"}), "fallback": self.fallback},
                    "position": self.positions.get(args["session"]), "enabled": self.enabled.get(args["session"], False)}}
        return super()._call(name, args)


def rpc(service, **args):
    return handle_rpc(service, {"method": "tools/call", "params": {
        "name": "tobkiri_cursor", "arguments": {"pid": 7, "window_id": 10, **args}}})


def test_native_theme_preserved_by_default_and_session_themes_are_independent():
    transport = ThemeTransport()
    with Computer(transport=transport, cursor_follow_interval=None) as computer:
        left = computer.mouse("left", pid=7, window_id=10)
        right = computer.mouse("right", pid=7, window_id=11)
        assert not any(name == "set_agent_cursor_theme" for name, _ in transport.calls)
        left.set_cursor_theme("tobkiri.stickman", reduced_motion="on")
        right.set_cursor_theme("cua.default")
        assert left.cursor_state()["theme"]["id"] == "tobkiri.stickman"
        assert right.cursor_state()["theme"]["id"] == "cua.default"
        assert transport.themes[left.session]["reduced_motion"] == "on"
        assert all(set(args) == {"session", "theme_id", "reduced_motion"}
                   for name, args in transport.calls if name == "set_agent_cursor_theme")
        assert not any(name in ("move_cursor", "click", "set_window_frame") for name, _ in transport.calls)


def test_arbitrary_installed_id_and_native_fallback_are_preserved(rig):
    transport = ThemeTransport()
    with Computer(transport=transport, cursor_theme="my.brand-cursor", cursor_reduced_motion="off",
                  cursor_follow_interval=None) as computer:
        window = computer.window(pid=7, window_id=10)
        transport.fallback = "render diagnostic from native driver"
        state = window.cursor_state()
        assert state["theme"]["id"] == "my.brand-cursor"
        assert state["theme"]["reduced_motion"] == "off"
        assert state["theme"]["fallback"] == transport.fallback


def test_theme_refusal_is_not_retried_and_failed_start_releases_session():
    transport = ThemeTransport()
    with Computer(transport=transport, cursor_theme="missing.theme", cursor_follow_interval=None) as computer:
        with pytest.raises(ComputerError, match="not installed"):
            computer.window(pid=7, window_id=10)
        assert len([args for name, args in transport.calls if name == "set_agent_cursor_theme"]) == 1
        assert len([args for name, args in transport.calls if name == "end_session"]) == 1
        assert not computer._sessions
        assert not any(name in ("move_cursor", "click") for name, _ in transport.calls)


def test_theme_changes_preserve_snapshot_coordinates_and_anchor(rig):
    computer, transport = rig
    window = computer.window(pid=7, window_id=10)
    state = window.observe()
    cursor = computer.cursor_status()
    calls = len(transport.calls)
    window.set_cursor_theme("tobkiri.arrow")
    assert [name for name, _ in transport.calls[calls:]] == ["set_agent_cursor_theme"]
    assert computer.cursor_status() == cursor
    assert computer._latest[window.surface] == state.id
    transport.bounds["x"] += 100
    window.click(state.point(10, 20))
    sent = next(args for name, args in transport.calls if name == "click")
    assert (sent["x"], sent["y"]) == (10, 20)


@pytest.mark.parametrize("theme_id", ["", "stickman", "../evil.theme", "/tmp/cursor.lottie",
                                      "C:\\themes\\pointer.cua-theme", "file://art.cua-theme",
                                      "a..b", "a." + "b" * 64, "a." + "b" * 199, {"id": "a.b"}])
def test_invalid_ids_send_nothing(rig, theme_id):
    computer, transport = rig
    window = computer.window(pid=7, window_id=10)
    calls = len(transport.calls)
    with pytest.raises(ValueError):
        window.set_cursor_theme(theme_id)
    assert len(transport.calls) == calls
    with pytest.raises(ValueError):
        Computer(transport=transport, cursor_theme=theme_id)
    assert len(transport.calls) == calls


def test_invalid_motion_does_not_dispatch(rig):
    computer, transport = rig
    window = computer.window(pid=7, window_id=10)
    calls = len(transport.calls)
    with pytest.raises(ValueError):
        window.set_cursor_theme("cua.default", reduced_motion="yes")
    with pytest.raises(ValueError):
        Computer(transport=transport, cursor_reduced_motion="yes")
    assert len(transport.calls) == calls


def test_mcp_select_and_read_state_do_not_require_observation_or_move_input():
    transport = ThemeTransport()
    with Computer(transport=transport, cursor_follow_interval=None) as computer:
        service = ToolService(computer)
        result = rpc(service, action="theme", theme_id="tobkiri.stickman", reduced_motion="on")
        assert result["structuredContent"]["theme"]["id"] == "tobkiri.stickman"
        transport.fallback = "native failure detail"
        state = rpc(service, action="state")["structuredContent"]
        assert state["theme"]["fallback"] == "native failure detail"
        error = rpc(service, action="theme", theme_id="missing.theme")
        assert error["isError"]
        assert error["structuredContent"]["error"]["code"] == "driver_error"
        assert not any(name in ("get_window_state", "move_cursor", "click") for name, _ in transport.calls)


@pytest.mark.parametrize("arguments", [{"action": "theme"}, {"action": "theme", "theme_id": "../evil.theme"},
                                       {"action": "theme", "theme_id": "cua.default", "reduced_motion": "yes"},
                                       {"action": "theme", "theme_id": "cua.default", "source": "art.lottie"}])
def test_mcp_invalid_theme_requests_allocate_no_session(rig, arguments):
    computer, transport = rig
    service = ToolService(computer)
    before = len(transport.calls)
    assert rpc(service, **arguments)["isError"]
    assert len(transport.calls) == before


@pytest.mark.parametrize("theme_id", BUILTIN_THEMES)
def test_portable_sources_are_reproducible_and_cover_all_native_actions(tmp_path, theme_id):
    first = write_source(theme_id, tmp_path / "first.lottie")
    second = write_source(theme_id, tmp_path / "second.lottie")
    assert first.read_bytes() == second.read_bytes()
    with ZipFile(first) as archive:
        manifest = json.loads(archive.read("cua/theme.json"))
        assert manifest["id"] == theme_id
        assert manifest["compatibility"] == {"profile": "cua-driver-actions-v2", "semantics": 2}
        assert set(manifest["actions"]) == set(ACTIONS)
        assert len(archive.namelist()) == 14
        artwork = []
        for action in ACTIONS:
            animation = json.loads(archive.read("a/action_" + action + ".json"))
            assert animation["assets"] == []
            assert animation["layers"]
            assert 0 <= manifest["actions"][action]["still_frame"] < animation["op"] <= 120
            artwork.append(animation["layers"])
        assert len({json.dumps(layers, sort_keys=True) for layers in artwork}) == len(ACTIONS)


def test_cua_default_is_embedded_and_not_regenerated(tmp_path):
    with pytest.raises(ValueError, match="embedded"):
        write_source("cua.default", tmp_path / "cua.default.lottie")
    assert not list(tmp_path.iterdir())


def test_os_packages_share_identical_artwork_generator():
    root = Path(__file__).resolve().parents[2]
    relative = Path("src/tobkiri_computer_use/cursor_themes.py")
    if (root / "mac" / relative).exists() and (root / "windows" / relative).exists():
        assert (root / "mac" / relative).read_bytes() == (root / "windows" / relative).read_bytes()


def test_host_cli_source_only_never_invokes_driver(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("source-only must not start the driver")
    monkeypatch.setattr(subprocess, "run", refuse)
    main(["tobkiri.stickman", "--source-only", "--output", str(tmp_path)])
    assert (tmp_path / "tobkiri.stickman.lottie").is_file()
    with pytest.raises(SystemExit):
        main(["tobkiri.stickman", "--source-only", "--install", "--output", str(tmp_path)])


def test_host_cli_compile_then_explicit_install_preserves_spaced_paths(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    main(["tobkiri.arrow", "--output", str(tmp_path / "a directory"),
          "--compiler", "/a path/cua-cursor-theme", "--install"])
    assert [args[1] for args, _ in calls] == ["build", "install"]
    assert all(args[0] == "/a path/cua-cursor-theme" and kwargs == {"check": True} for args, kwargs in calls)
    assert calls[0][0][4] == calls[1][0][2]


def test_host_cli_compilation_failure_never_installs_or_retries(tmp_path, monkeypatch):
    calls = []
    def fail(args, **kwargs):
        calls.append(args)
        raise subprocess.CalledProcessError(2, args)
    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        main(["tobkiri.stickman", "--output", str(tmp_path), "--install"])
    assert len(calls) == 1
    assert calls[0][:3] == ["cua-driver", "cursor-theme", "build"]
