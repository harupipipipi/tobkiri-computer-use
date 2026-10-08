"""Keep the MCP connection open while replacing an idle Tobkiri worker.

Only an explicit local publish or runtime reload activates installed code. No
file watcher imports half-written edits, and no input is replayed on failure.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import uuid

from .transport import ComputerError, McpTransport, structured


PACKAGE = Path(__file__).resolve().parent
RUNTIME_TOOL = {
    "name": "tobkiri_runtime",
    "description": "Read the loaded Tobkiri version or reload its installed worker without restarting the MCP client. Reload waits for this connection's current operation to finish, discards observations/sessions, and never retries input. Reobserve afterward. It does not install code, alter grants, or restart Cua.",
    "inputSchema": {"type": "object", "properties": {
        "action": {"enum": ["status", "reload"], "default": "status"}},
        "additionalProperties": False},
}
# After replacing the worker, do not forward an action using old observations.
# Other tools remain usable after the caller has seen runtime_reloaded.
FRESH_READS = {"tobkiri_runtime", "tobkiri_tools", "tobkiri_windows", "tobkiri_observe",
               "list_apps", "list_windows", "get_window_state", "get_desktop_state",
               "get_accessibility_tree", "get_agent_cursor_state"}


def result(value, *, error=False):
    out = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
           "structuredContent": value}
    if error:
        out["isError"] = True
    return out


def source_digest(package=PACKAGE):
    digest = hashlib.sha256()
    paths = sorted(set(package.rglob("*.py")) | set((package / "skill").rglob("*.md")))
    for path in paths:
        data = path.read_bytes()
        if path.suffix == ".py":
            compile(data, str(path), "exec")  # validate without executing code
        digest.update(str(path.relative_to(package)).encode() + b"\0" + data + b"\0")
    return digest.hexdigest()


def marker_path():
    key = hashlib.sha256(str(PACKAGE).encode()).hexdigest()[:16]
    return Path.home() / ".config/tobkiri-computer-use" / f"reload-{key}.json"


def read_marker(path):
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or not isinstance(value.get("revision"), str) or not isinstance(value.get("digest"), str):
        raise ValueError("Invalid Tobkiri reload marker")
    return value


def publish(path=None):
    path = path or marker_path()
    value = {"revision": uuid.uuid4().hex, "digest": source_digest()}
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + "." + value["revision"] + ".tmp")
    try:
        with temporary.open("x") as output:
            json.dump(value, output)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return value


def start_worker(command):
    # A host can time out sooner. Keep draining the operation rather than
    # replacing a worker that may still be delivering input.
    # A same-size edit within one timestamp tick must not reuse stale .pyc.
    # A unique nonexistent cache root + -B reads source and writes no cache.
    cache = str(Path(tempfile.gettempdir()) / ("tobkiri-no-cache-" + uuid.uuid4().hex))
    fresh = [command[0], "-B", "-X", f"pycache_prefix={cache}", *command[1:]]
    return McpTransport(fresh, timeout=3600)


class ReloadableServer:
    def __init__(self, command, *, factory=start_worker, marker=None, notify=None):
        self.command = list(command)  # startup policy is fixed, never a tool argument
        self.factory = factory
        self.marker = marker or marker_path()
        self.notify = notify or (lambda message: None)
        self._lock = threading.RLock()
        self.revision = read_marker(self.marker)
        self.worker = factory(self.command)
        self.generation = 1
        self.reload_error = None
        self.uncertain = False

    def close(self):
        with self._lock:
            self.worker.close()

    def status(self):
        return {"runtime_version": self.worker.server_info.get("version"),
                "generation": self.generation, "restartless_reload": True,
                "worker_pid": getattr(getattr(self.worker, "proc", None), "pid", None),
                "supervisor_pid": os.getpid(), "reload_error": self.reload_error,
                "worker_outcome_unknown": self.uncertain,
                "observations_reset_on_reload": True}

    def reload(self, revision, *, verify_marker=True):
        if self.uncertain:
            raise ComputerError("worker_outcome_unknown", "A request timed out or disconnected; no automatic reload or retry. Inspect the target independently before reconnecting MCP.")
        replacement = None
        try:
            # Explicit reload may load current installed files without publishing.
            digest = source_digest()
            if verify_marker and revision and revision["digest"] != digest:
                raise ValueError("Installed files changed after publish; finish the update and publish again")
            replacement = self.factory(self.command)
            replacement.list_tools()  # validate startup before releasing old sessions
            if source_digest() != digest:
                raise ValueError("Installed files changed during reload; publish a finished update")
        except Exception as exc:
            if replacement:
                replacement.close()
            self.reload_error = str(exc)
            raise ComputerError("reload_failed", "Old worker retained; no input was forwarded", details=str(exc)) from exc
        old, self.worker = self.worker, replacement
        self.revision, self.reload_error = revision, None
        self.generation += 1
        old.close()  # idle worker only; the shared Cua daemon remains alive
        self.notify({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})
        self.notify({"jsonrpc": "2.0", "method": "notifications/resources/list_changed"})

    def request(self, method, params=None):
        with self._lock:
            params = params or {}
            # The existing generic call remains a route to newly added helpers,
            # even when the host retains an older advertised tool list.
            if method == "tools/call" and params.get("name") == "tobkiri_call":
                inner = params.get("arguments", {})
                if isinstance(inner, dict) and str(inner.get("name", "")).startswith("tobkiri_"):
                    if set(inner) - {"name", "arguments"} or inner["name"] == "tobkiri_call":
                        return result({"error": {"code": "invalid_arguments", "message": "Invalid helper call"}}, error=True)
                    params = {"name": inner["name"], "arguments": inner.get("arguments", {})}
            name = params.get("name") if method == "tools/call" else None
            if name == "tobkiri_runtime":
                args = params.get("arguments", {})
                if not isinstance(args, dict) or set(args) - {"action"} or args.get("action", "status") not in ("status", "reload"):
                    return result({"error": {"code": "invalid_arguments", "message": "Use action=status or reload"}}, error=True)
            revision = read_marker(self.marker)
            changed = revision != self.revision
            if self.uncertain:
                if name == "tobkiri_runtime" and params.get("arguments", {}).get("action", "status") == "status":
                    return result(self.status())
                raise ComputerError("worker_outcome_unknown", "No input or reload was sent after the uncertain request; inspect the target independently before reconnecting MCP.")
            explicit = name == "tobkiri_runtime" and params.get("arguments", {}).get("action") == "reload"
            if changed or explicit:
                self.reload(revision, verify_marker=not explicit)
                if name and name not in FRESH_READS:
                    return result({"error": {"code": "runtime_reloaded", "message": "Updated worker; this action was NOT sent. Observe again before using coordinates, tokens or browser bindings."},
                                   "runtime": self.status()}, error=True)
            if method == "initialize":
                initial = deepcopy(self.worker.initialize_result)
                initial.setdefault("capabilities", {}).setdefault("tools", {})["listChanged"] = True
                initial["capabilities"].setdefault("resources", {})["listChanged"] = True
                return initial
            if method == "tools/list":
                return {"tools": self.worker.list_tools() + [deepcopy(RUNTIME_TOOL)]}
            if name == "tobkiri_runtime":
                return result(self.status())
            if name == "tobkiri_tools":
                requested = params.get("arguments", {}).get("name")
                if requested == RUNTIME_TOOL["name"]:
                    return result(RUNTIME_TOOL)
                if requested and requested.startswith("tobkiri_"):
                    descriptor = next((t for t in self.worker.list_tools() if t["name"] == requested), None)
                    if descriptor:
                        return result(descriptor)
                response = self.forward(method, params)
                if not requested and not response.get("isError"):
                    index = structured(response)
                    index["runtime"] = self.status()
                    index["helpers"] = [{"name": t["name"], "description": t.get("description", "")}
                                        for t in self.worker.list_tools() + [RUNTIME_TOOL] if t["name"].startswith("tobkiri_")]
                    return result(index)
                return response
            # Preserve native result/errors, and never resend an uncertain call.
            return self.forward(method, params)

    def forward(self, method, params):
        try:
            return self.worker.request(method, params)
        except ComputerError as exc:
            if exc.code in ("timeout", "transport_closed"):
                self.uncertain = True
            raise


def main():
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        from .server import main as worker_main
        return worker_main()
    def emit(value):
        print(json.dumps(value, ensure_ascii=False), flush=True)
    service = ReloadableServer([sys.executable, "-m", "tobkiri_computer_use.server", *sys.argv[1:]], notify=emit)
    try:
        for line in sys.stdin:
            request_id = None
            message = {}
            try:
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError("JSON-RPC request must be an object")
                if "id" not in message:
                    continue
                request_id = message["id"]
                response = service.request(message.get("method"), message.get("params"))
                emit({"jsonrpc": "2.0", "id": request_id, "result": response})
            except Exception as exc:
                if isinstance(exc, ComputerError) and message.get("method") == "tools/call":
                    emit({"jsonrpc": "2.0", "id": request_id, "result": result({"error": exc.as_dict()}, error=True)})
                else:
                    emit({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": str(exc)}})
    finally:
        service.close()


def reload_main():
    parser = argparse.ArgumentParser(description="Publish installed Tobkiri code for reload at each MCP connection's next request boundary; no Codex restart.")
    parser.parse_args()
    value = publish()
    print(json.dumps({"status": "published", **value,
                     "activation": "Each reloadable MCP connection switches before its next request. Running actions finish first; old observations expire. Legacy 0.1.5 connections need one MCP-only reconnect."}))


if __name__ == "__main__":
    main()
