import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tobkiri_computer_use import runtime


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / "runtime.json"
    monkeypatch.setattr(runtime, "config_path", lambda: path)
    driver = tmp_path / "cua-driver.exe"
    driver.write_bytes(b"driver")
    data = {
        "version": 2,
        "platform": "windows",
        "driver": str(driver),
        "socket": runtime.DEFAULT_PIPE,
        "permission_mode": "standard",
        "grants": ["existing-profile"],
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def test_python_and_mcp_share_saved_pipe(config, monkeypatch):
    calls = []
    monkeypatch.setattr(runtime, "ensure_runtime", calls.append)
    expected = [str(Path(config["driver"]).resolve()), "mcp", "--socket", runtime.DEFAULT_PIPE]
    assert runtime.driver_command() == expected
    assert runtime.driver_command(driver=config["driver"]) == expected
    assert calls == [config, config]


def test_explicit_host_pipe_never_starts_or_reads_config(config, monkeypatch):
    monkeypatch.setattr(runtime, "ensure_runtime", lambda _: pytest.fail("host owns lifecycle"))
    runtime.config_path().write_text("broken", encoding="utf-8")
    assert runtime.driver_command(driver=config["driver"], endpoint=r"\\.\pipe\host-cua") == [
        str(Path(config["driver"]).resolve()), "mcp", "--socket", r"\\.\pipe\host-cua"]


def test_missing_config_preserves_unconfigured_default(config):
    runtime.config_path().unlink()
    assert runtime.driver_command() == ["cua-driver", "mcp"]


@pytest.mark.parametrize("field,value", [
    ("permission_mode", "unrestricted"),
    ("grants", ["unknown"]),
    ("socket", r"\\.\pipe\other"),
    ("platform", "macos"),
])
def test_invalid_config_does_not_fall_back(config, field, value):
    config[field] = value
    runtime.config_path().write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError):
        runtime.driver_command()


def test_live_daemon_is_reused(config, monkeypatch):
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.setattr(runtime, "daemon_running", lambda _: True)
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *a, **k: pytest.fail("must not restart"))
    runtime.ensure_runtime(config)


def test_cold_launch_is_hidden_standard_and_only_uses_saved_grant(config, monkeypatch):
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    states = iter([False, True])
    monkeypatch.setattr(runtime, "daemon_running", lambda _: next(states))
    calls = []
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda a, **k: calls.append((a, k)))
    runtime.ensure_runtime(config)
    command, kwargs = calls[0]
    assert command == [config["driver"], "serve", "--socket", runtime.DEFAULT_PIPE,
                       "--permission-mode", "standard", "--grant", "existing-profile"]
    assert kwargs["creationflags"] == runtime._hidden_creation_flags()
    assert kwargs["stdin"] is runtime.subprocess.DEVNULL


def test_wrong_driver_cannot_reuse_configured_pipe(config, tmp_path):
    other = tmp_path / "other.exe"
    other.write_bytes(b"other")
    with pytest.raises(ValueError, match="differs"):
        runtime.driver_command(driver=str(other))


def test_daemon_running_requires_success_and_positive_status(tmp_path, monkeypatch):
    driver = tmp_path / "cua-driver.exe"
    driver.write_bytes(b"driver")
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout="Cua Driver daemon is running"))
    assert runtime.daemon_running(driver)
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=1, stdout="Cua Driver daemon is not running"))
    assert not runtime.daemon_running(driver)
