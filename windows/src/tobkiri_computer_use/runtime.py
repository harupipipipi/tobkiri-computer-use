"""Trusted Windows startup configuration shared by the Python and MCP APIs.

The managed process always uses Cua Driver's standard permission mode. Browser
profile access is an explicit setup-time grant; ordinary tool calls cannot add
it. The daemon is started in the signed-in interactive Windows session without
opening a console window.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


CONFIG_VERSION = 2
DEFAULT_PIPE = r"\\.\pipe\cua-driver"


def config_path():
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return root / "Tobkiri Computer Use" / "runtime.json"


def _absolute_executable(value):
    resolved = shutil.which(value) or value
    path = Path(resolved).expanduser()
    if not path.is_absolute():
        raise ValueError("The Cua Driver executable must resolve to an absolute path")
    return path.resolve(strict=True)


def read_config():
    path = config_path()
    if not path.exists():
        return None
    config = json.loads(path.read_text(encoding="utf-8"))
    grants = config.get("grants")
    valid = (
        config.get("version") == CONFIG_VERSION
        and config.get("platform") == "windows"
        and config.get("permission_mode") == "standard"
        and grants in ([], ["existing-profile"])
        and isinstance(config.get("driver"), str)
        and Path(config["driver"]).is_absolute()
        and config.get("socket") == DEFAULT_PIPE
    )
    if not valid:
        raise ValueError(f"Invalid Tobkiri Windows runtime configuration: {path}")
    return config


def daemon_running(driver):
    result = subprocess.run(
        [str(driver), "status"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=10,
    )
    return result.returncode == 0 and "daemon is running" in result.stdout.casefold()


def _hidden_creation_flags():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def ensure_runtime(config):
    if sys.platform != "win32":
        raise RuntimeError("The managed Windows runtime requires Windows")
    driver = _absolute_executable(config["driver"])
    if daemon_running(driver):
        return
    command = [str(driver), "serve", "--socket", config["socket"],
               "--permission-mode", "standard"]
    for grant in config["grants"]:
        command.extend(("--grant", grant))
    subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=_hidden_creation_flags(),
    )
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if daemon_running(driver):
            return
        time.sleep(.15)
    raise RuntimeError(
        "Tobkiri could not start Cua Driver in the interactive Windows session. "
        "Run `cua-driver doctor` and `cua-driver status`."
    )


def driver_command(*, driver=None, endpoint=None):
    if endpoint:
        return [str(_absolute_executable(driver or "cua-driver")), "mcp", "--socket", endpoint]
    config = read_config()
    if not config:
        return [driver or "cua-driver", "mcp"]
    selected = _absolute_executable(driver or config["driver"])
    configured = _absolute_executable(config["driver"])
    if selected != configured:
        raise ValueError("--driver differs from the configured runtime; use it or rerun setup")
    ensure_runtime(config)
    return [str(configured), "mcp", "--socket", config["socket"]]


def main():
    parser = argparse.ArgumentParser(
        description="Configure Tobkiri's Windows Cua Driver runtime in standard mode."
    )
    parser.add_argument("--driver", default="cua-driver")
    parser.add_argument(
        "--existing-profile", action="store_true",
        help="Allow the runtime to attach to an already signed-in Chrome/Edge profile.",
    )
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("This setup command is for Windows")
    binary = _absolute_executable(args.driver)
    config = {
        "version": CONFIG_VERSION,
        "platform": "windows",
        "driver": str(binary),
        "socket": DEFAULT_PIPE,
        "permission_mode": "standard",
        "grants": ["existing-profile"] if args.existing_profile else [],
    }
    ensure_runtime(config)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(json.dumps({
        "configured": str(path),
        "driver": str(binary),
        "socket": DEFAULT_PIPE,
        "permission_mode": "standard",
        "existing_profile": args.existing_profile,
        "background_input": "default",
        "foreground_input": "per_action_approval",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
