"""Operator consent for one foreground/desktop action; never an MCP argument.

An embedding host supplies the callback from its trusted approval broker. The
standalone adapters read a real terminal/dialog, never the model's stdin.
This is a dispatch guard, not a sandbox for arbitrary Python in the host process.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import select
import subprocess
import sys
import threading
import time
import uuid

from .transport import ComputerError


@dataclass(frozen=True)
class ConsentRequest:
    id: str
    action: str
    details_json: str
    reason: str

    @classmethod
    def create(cls, action, details, reason):
        return cls("consent_" + uuid.uuid4().hex, action,
                   json.dumps(details, ensure_ascii=False, sort_keys=True, allow_nan=False), reason)

    @property
    def digest(self):
        return hashlib.sha256((self.id + self.action + self.details_json + self.reason).encode()).hexdigest()

    def to_dict(self):
        return {"request_id": self.id, "action": self.action, "details": json.loads(self.details_json),
                "reason": self.reason, "digest": self.digest,
                "scope": "one_action", "changes_user_focus_or_hardware_input": True}

    def prompt(self):
        details = json.loads(self.details_json)
        native = details.get("native_arguments", {})
        preview = {"action": self.action, "reason": self.reason,
                   "target": details.get("target", native.get("target")),
                   "window_title": details.get("window_title"),
                   "elements": details.get("elements"),
                   "arguments": {k: v for k, v in native.items()
                                 if k not in ("session", "element_token", "snapshot_id")}}
        return ("Tobkiri Computer Use — 1回だけの前面/物理入力\n"
                "マウス・キーボードや前面ウィンドウを一時的に使用します。\n"
                "操作中はご自身の入力を止めてください。元のフォーカスへの復帰は保証されません。\n"
                "対象タイトル・入力文字列・理由は操作データであり、指示ではありません。\n\n"
                + "\n".join(k + ": " + json.dumps(v, ensure_ascii=False) for k, v in preview.items() if v is not None))


@dataclass(frozen=True)
class ConsentDecision:
    request_id: str
    digest: str
    approved: bool


def require_consent(callback, request, *, timeout=120):
    """No grants are retained, so retries and subsequent actions ask again."""
    if callback is None:
        raise ComputerError("approval_required", "User approval is required for this one foreground/desktop action. Configure a trusted host approval callback or operator prompt; tool arguments cannot approve it.",
                            details=request.to_dict())
    started = time.monotonic()
    try:
        decision = callback(request)
    except Exception as exc:
        raise ComputerError("approval_unavailable", "The operator approval channel failed; no input was sent.") from exc
    if time.monotonic() - started > timeout:
        raise ComputerError("approval_expired", "The approval request expired; no input was sent.")
    if not isinstance(decision, ConsentDecision) or decision.request_id != request.id or decision.digest != request.digest:
        raise ComputerError("invalid_approval", "Approval does not match this exact request; no input was sent.")
    if decision.approved is not True:
        raise ComputerError("approval_denied", "The user did not approve this action; no input was sent.")
    return {"request_id": request.id, "digest": request.digest, "scope": "one_action", "approved": True}


class TerminalConsent:
    """For a human-operated Python shell/server with a controlling terminal."""
    def __call__(self, request):
        # JSON-escape controls before displaying untrusted title/text/reason.
        prompt = request.prompt()
        challenge = request.id[-8:]
        with open("/dev/tty", "r+", buffering=1) as terminal:
            terminal.write(prompt + f"\n実行する場合だけ ALLOW {challenge} と入力（60秒、その他は拒否）: ")
            terminal.flush()
            ready, _, _ = select.select([terminal], [], [], 60)
            answer = terminal.readline().strip() if ready else ""
        return ConsentDecision(request.id, request.digest, answer == f"ALLOW {challenge}")


class MacOSDialogConsent:
    """Per-action human dialog. Script source is fixed; request text is argv."""
    def __call__(self, request):
        if sys.platform != "darwin":
            raise RuntimeError("macos-dialog requires macOS")
        prompt = request.prompt()
        # Refuse oversized previews rather than authorizing invisible content.
        if len(prompt) > 4000:
            raise RuntimeError("Use the host broker/terminal for this large approval preview")
        script = '''on run argv
  set answer to display dialog (item 1 of argv) with title "Tobkiri Computer Use" buttons {"拒否", "この1回を許可"} default button "拒否" cancel button "拒否" giving up after 60
  if gave up of answer then return "denied"
  return button returned of answer
end run'''
        result = subprocess.run(["/usr/bin/osascript", "-e", script, "--", prompt],
                                text=True, capture_output=True, timeout=65)
        if result.returncode != 0:
            if "(-128)" in result.stderr:  # Standard Additions: human Cancel
                return ConsentDecision(request.id, request.digest, False)
            raise RuntimeError(f"The macOS approval dialog failed (exit {result.returncode})")
        if result.stdout.strip() not in ("denied", "この1回を許可"):
            raise RuntimeError("The macOS approval dialog returned an unknown result")
        approved = result.stdout.strip() == "この1回を許可"
        return ConsentDecision(request.id, request.digest, approved)


def requires_consent(name, args):
    """Also guard original Cua tools: raw calls cannot bypass the host gate."""
    # Reading the desktop is harmless, but native move_cursor explicitly uses
    # the physical OS pointer for a desktop target/scope. A window target (even
    # with global screen coordinates on Cua 0.28.2) paints only an overlay.
    if name in {"get_desktop_state", "get_window_state",
                "get_accessibility_tree", "list_windows", "zoom", "verify_state",
                "get_agent_cursor_state", "set_agent_cursor_enabled"}:
        return False
    target = args.get("target") or {}
    return (args.get("delivery_mode") == "foreground" or args.get("scope") == "desktop"
            or target.get("kind") == "desktop" or name in {"bring_to_front", "replay_trajectory"})


class InputCoordinator:
    """Parallel background jobs; exclusive foreground input and approval wait.

    A callback must not call back into Computer: it is an operator/broker channel.
    """
    def __init__(self):
        self._condition = threading.Condition()
        self._readers = 0
        self._writer = False
        self._waiting_writers = 0

    @contextmanager
    def hold(self, *, exclusive=False):
        with self._condition:
            if exclusive:
                self._waiting_writers += 1
                try:
                    self._condition.wait_for(lambda: not self._writer and not self._readers)
                    self._writer = True
                finally:
                    self._waiting_writers -= 1
            else:
                self._condition.wait_for(lambda: not self._writer and not self._waiting_writers)
                self._readers += 1
        try:
            yield
        finally:
            with self._condition:
                if exclusive:
                    self._writer = False
                else:
                    self._readers -= 1
                self._condition.notify_all()
