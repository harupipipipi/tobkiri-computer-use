"""Trusted local startup configuration shared by Python and MCP.

Only the explicit setup CLI writes the profile grant. Ordinary tool calls do
not widen permissions. A private LaunchServices daemon preserves Cua's macOS
identity and leaves other clients' shared daemon running.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time


def config_path():
    return Path.home() / ".config/tobkiri-computer-use/runtime.json"


def read_config():
    path = config_path()
    if not path.exists():
        return None
    config = json.loads(path.read_text())
    if (config.get("version") != 1 or config.get("permission_mode") != "standard"
            or config.get("grants") != ["existing-profile"]
            or not all(isinstance(config.get(k), str) and Path(config[k]).is_absolute()
                       for k in ("driver", "app", "socket"))):
        raise ValueError(f"Invalid Tobkiri runtime configuration: {path}")
    return config


def listening(endpoint):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(.25)
        try:
            client.connect(endpoint)
            return True
        except (OSError, TimeoutError):
            return False


def managed_socket(binary):
    """Keep each executable build separate from any already-running daemon.

    A socket accepting connections is not evidence that it serves the newly
    selected binary. Include both its bundle path (code identity) and contents
    so setup can coexist with, rather than restart, a previous runtime.
    """
    binary = Path(binary).resolve(strict=True)
    digest = hashlib.sha256(os.fsencode(binary))
    with binary.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return Path.home() / "Library/Caches/tobkiri-computer-use" / f"driver-{digest.hexdigest()[:16]}.sock"


def ensure_runtime(config):
    if listening(config["socket"]):
        return
    if sys.platform != "darwin":
        raise RuntimeError("This managed runtime uses macOS LaunchServices. Supply an explicit driver command on other platforms.")
    import fcntl
    directory = Path(config["socket"]).parent
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Several Python/MCP clients may reconnect together after login.
    with (directory / "startup.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if listening(config["socket"]):
            return
        subprocess.run([
            "/usr/bin/open", "-n", "-g", "-a", config["app"], "--args",
            "serve", "--socket", config["socket"], "--permission-mode", "standard",
            "--grant", "existing-profile",
        ], check=True, capture_output=True, text=True, timeout=10)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if listening(config["socket"]):
                return
            time.sleep(.1)
    raise RuntimeError("Tobkiri's configured Cua daemon did not start. Check CuaDriver's OS permissions; no fallback runtime was selected.")


def driver_command(*, driver=None, endpoint=None):
    # Explicit host endpoints never launch or change another runtime.
    if endpoint:
        return [driver or "cua-driver", "mcp", "--socket", endpoint]
    config = read_config()
    if config:
        if driver and Path(shutil.which(driver) or driver).resolve() != Path(config["driver"]).resolve():
            raise ValueError("--driver differs from the configured runtime; supply --socket for that host or rerun setup.")
        ensure_runtime(config)
        return [config["driver"], "mcp", "--socket", config["socket"]]
    return [driver or "cua-driver", "mcp"]


def main():
    parser = argparse.ArgumentParser(description="Configure Tobkiri's dedicated standard-mode Cua runtime; does not restart the shared daemon.")
    parser.add_argument("--existing-profile", action="store_true", required=True,
                        help="Authorize routine attachment to existing logged-in browsers. Physical input still requires approval.")
    parser.add_argument("--driver", default="cua-driver")
    args = parser.parse_args()
    binary = Path(shutil.which(args.driver) or args.driver).resolve(strict=True)
    app = next((p for p in binary.parents if p.suffix == ".app"), None)
    if sys.platform != "darwin" or app is None:
        parser.error("Use the installed macOS CuaDriver.app executable for managed setup.")
    config = {"version": 1, "driver": str(binary), "app": str(app),
              "socket": str(managed_socket(binary)),
              "permission_mode": "standard", "grants": ["existing-profile"]}
    ensure_runtime(config)
    path = config_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        os.chmod(temporary, 0o600)
        json.dump(config, stream, indent=2)
        stream.write("\n")
    temporary.replace(path)
    print(json.dumps({"configured": str(path), "socket": config["socket"],
                      "permission_mode": "standard", "existing_profile": True,
                      "physical_input": "per_action_approval", "shared_daemon_restarted": False}))


if __name__ == "__main__":
    main()
