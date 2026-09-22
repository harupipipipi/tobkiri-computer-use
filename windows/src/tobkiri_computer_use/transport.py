"""Multiplexed, newline-delimited MCP transport. No shared response queue."""
from __future__ import annotations

from concurrent.futures import Future, TimeoutError as FutureTimeout
import itertools
import json
import subprocess
import threading
from typing import Any
from .version import VERSION
from .runtime import driver_command


class ComputerError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Any = None):
        super().__init__(message)
        self.code, self.details = code, details

    def as_dict(self):
        return {"code": self.code, "message": str(self), "details": self.details}


def structured(result: dict) -> dict:
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    for block in result.get("content", []):
        if block.get("type") == "text":
            try:
                value = json.loads(block["text"])
                if isinstance(value, dict):
                    return value
            except (ValueError, TypeError):
                pass
    return {}


class McpTransport:
    def __init__(self, command=None, timeout=180.0):
        self.timeout = timeout
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._pending: dict[int, Future] = {}
        self._closed = False
        self.proc = subprocess.Popen(
            command if command is not None else driver_command(), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=None, text=True, encoding="utf-8", bufsize=1,
        )
        self._reader_thread = threading.Thread(target=self._reader, daemon=True)
        self._reader_thread.start()
        try:
            self.initialize_result = self.request("initialize", {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "tobkiri-computer-use", "version": VERSION},
            })
            self.server_info = self.initialize_result.get("serverInfo", {})
            self.notify("notifications/initialized")
        except BaseException:
            self.close()
            raise

    def _reader(self):
        try:
            for line in self.proc.stdout:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue  # vendor diagnostic, never interpreted as a response
                if not isinstance(message, dict) or "id" not in message:
                    continue
                with self._lock:
                    pending = self._pending.pop(message["id"], None)
                if pending is not None:
                    if "error" in message:
                        pending.set_exception(ComputerError(
                            "rpc_error", str(message["error"]), details=message["error"]))
                    else:
                        pending.set_result(message.get("result", {}))
        finally:
            self._fail_all(ComputerError("transport_closed", "Driver disconnected; re-open Computer."))

    def _fail_all(self, exc):
        with self._lock:
            self._closed = True
            futures = list(self._pending.values())
            self._pending.clear()
        for future in futures:
            future.set_exception(exc)

    def _write(self, message):
        self.proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def notify(self, method, params=None):
        with self._lock:
            if self._closed:
                raise ComputerError("transport_closed", "Driver is closed.")
            self._write({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def request(self, method, params=None, *, timeout=None):
        with self._lock:
            if self._closed:
                raise ComputerError("transport_closed", "Driver is closed.")
            request_id, future = next(self._ids), Future()
            self._pending[request_id] = future
            try:
                self._write({"jsonrpc": "2.0", "id": request_id,
                             "method": method, "params": params or {}})
            except (OSError, ValueError) as exc:
                self._pending.pop(request_id, None)
                raise ComputerError("transport_closed", str(exc)) from exc
        try:
            return future.result(timeout=self.timeout if timeout is None else timeout)
        except FutureTimeout as exc:
            with self._lock:
                self._pending.pop(request_id, None)
            # The operation may still finish. Never retry input automatically.
            raise ComputerError("timeout", f"{method} timed out; input outcome is unknown. Observe before retrying.") from exc

    def call(self, name, arguments=None):
        result = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        if result.get("isError"):
            message = "\n".join(b.get("text", "") for b in result.get("content", []) if b.get("type") == "text")
            raise ComputerError("driver_error", f"{name}: {message}", details=result)
        return result

    def list_tools(self):
        tools, cursor = [], None
        while True:
            result = self.request("tools/list", {"cursor": cursor} if cursor else {})
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                return tools

    def close(self):
        self._fail_all(ComputerError("transport_closed", "Computer was closed."))
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2)
        self.proc.stdout.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
