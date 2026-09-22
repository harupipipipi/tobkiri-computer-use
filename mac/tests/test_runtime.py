import json
from pathlib import Path
import subprocess

import pytest

from tobkiri_computer_use import runtime


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / "runtime.json"
    monkeypatch.setattr(runtime, "config_path", lambda: path)
    data = {"version": 1, "driver": "/Applications/CuaDriver.app/Contents/MacOS/cua-driver",
            "app": "/Applications/CuaDriver.app", "socket": str(tmp_path / "driver.sock"),
            "permission_mode": "standard", "grants": ["existing-profile"]}
    path.write_text(json.dumps(data))
    return data


def test_python_and_mcp_share_saved_socket(config, monkeypatch):
    calls = []
    monkeypatch.setattr(runtime, "ensure_runtime", calls.append)
    assert runtime.driver_command() == runtime.driver_command(driver=config["driver"])
    assert runtime.driver_command() == [config["driver"], "mcp", "--socket", config["socket"]]
    assert calls == [config, config, config]


def test_explicit_host_socket_never_starts_or_reads_managed_config(config, monkeypatch):
    monkeypatch.setattr(runtime, "ensure_runtime", lambda _: pytest.fail("Host owns lifecycle"))
    runtime.config_path().write_text("broken")
    assert runtime.driver_command(driver="host-cua", endpoint="/host/private.sock") == [
        "host-cua", "mcp", "--socket", "/host/private.sock"]


def test_missing_config_preserves_unconfigured_default(config):
    runtime.config_path().unlink()
    assert runtime.driver_command() == ["cua-driver", "mcp"]


@pytest.mark.parametrize("field,value", [("permission_mode", "unrestricted"),
                                         ("grants", []), ("socket", "relative.sock")])
def test_invalid_config_does_not_fall_back_to_other_runtime(config, field, value):
    config[field] = value
    runtime.config_path().write_text(json.dumps(config))
    with pytest.raises(ValueError):
        runtime.driver_command()


def test_live_private_daemon_is_reused(config, monkeypatch):
    monkeypatch.setattr(runtime, "listening", lambda _: True)
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **k: pytest.fail("Must not restart"))
    runtime.ensure_runtime(config)


def test_cold_launch_keeps_standard_and_only_explicit_profile_grant(config, monkeypatch):
    states = iter([False, False, True])
    monkeypatch.setattr(runtime, "listening", lambda _: next(states))
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    calls = []
    monkeypatch.setattr(runtime.subprocess, "run", lambda a, **k: calls.append(a))
    runtime.ensure_runtime(config)
    assert calls == [["/usr/bin/open", "-n", "-g", "-a", config["app"], "--args",
                      "serve", "--socket", config["socket"], "--permission-mode", "standard",
                      "--grant", "existing-profile"]]


def test_launch_failure_never_selects_shared_daemon(config, monkeypatch):
    monkeypatch.setattr(runtime, "listening", lambda _: False)
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    def failed(*a, **k): raise subprocess.CalledProcessError(1, a)
    monkeypatch.setattr(runtime.subprocess, "run", failed)
    with pytest.raises(subprocess.CalledProcessError):
        runtime.driver_command()


def test_wrong_driver_cannot_implicitly_reuse_configured_endpoint(config):
    with pytest.raises(ValueError, match="differs"):
        runtime.driver_command(driver="/different/cua-driver")


def test_setup_selects_new_socket_for_new_binary_or_bundle(tmp_path):
    binary = tmp_path / "cua-driver"
    binary.write_bytes(b"first build")
    original = runtime.managed_socket(binary)
    assert runtime.managed_socket(binary) == original
    binary.write_bytes(b"patched build")
    updated = runtime.managed_socket(binary)
    assert updated != original
    other_bundle = tmp_path / "cua-driver-local"
    other_bundle.write_bytes(binary.read_bytes())
    assert runtime.managed_socket(other_bundle) != updated


def test_setup_never_reuses_old_live_endpoint(config, tmp_path, monkeypatch):
    binary = tmp_path / "CuaDriverLocal.app/Contents/MacOS/cua-driver-local"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"patched driver")
    selected = []
    monkeypatch.setattr(runtime, "ensure_runtime", selected.append)
    monkeypatch.setattr(runtime.sys, "platform", "darwin")
    monkeypatch.setattr(runtime.sys, "argv", ["setup", "--existing-profile", "--driver", str(binary)])
    runtime.main()
    assert selected[0]["socket"] != config["socket"]
    assert selected[0]["socket"] == str(runtime.managed_socket(binary))
    assert runtime.read_config()["socket"] == selected[0]["socket"]
