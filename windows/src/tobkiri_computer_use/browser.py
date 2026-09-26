"""Session-bound background browser operations; never activates a user's tab."""
from __future__ import annotations

import uuid
from .transport import ComputerError, structured
from .version import VERSION


OPERATIONS = {"state": "get_browser_state", "navigate": "browser_navigate",
              "click": "browser_click", "type": "browser_type", "pointer": "browser_pointer",
              "dialog": "browser_dialog"}


class Browser:
    """One exact browser window and one private lifecycle session.

    bind() returns native target/tab IDs; pass those IDs to call(). A native
    window handle is never substituted for a browser tab. Driver refusals stay
    refusals; this class never falls back to address bars or foreground input.
    """
    def __init__(self, computer, pid, window_id):
        if not isinstance(pid, int) or not isinstance(window_id, int) or pid <= 0 or window_id < 0:
            raise ComputerError("invalid_target", "Choose an observed pid/window_id.")
        self.computer = computer
        self.surface = (pid, window_id)
        self.session = "browser-" + uuid.uuid4().hex[:12]
        self.id = "b_" + uuid.uuid4().hex
        self._closed = False
        computer.transport.call("start_session", {"session": self.session})
        computer._sessions.add(self.session)
        computer.transport.call("set_agent_cursor_enabled", {"session": self.session, "enabled": False})

    def _check(self):
        if self._closed or self.computer._closed:
            raise ComputerError("closed", "This browser session is closed.")

    def bind(self):
        self._check()
        return self.computer.tool("get_browser_state", {
            "pid": self.surface[0], "window_id": self.surface[1], "session": self.session})

    def prepare(self, *, isolated=False, allow_launch=False):
        self._check()
        args = {"pid": self.surface[0], "session": self.session}
        if isolated:
            # Supplying an existing PID makes Cua return already_prepared for
            # that process, even with isolated_new. A new isolated launch must
            # instead use its attested system-browser discovery path.
            if allow_launch:
                args.pop("pid")
            args.update(profile={"mode": "isolated_new"}, allow_launch=allow_launch)
        else:
            args.update(window_id=self.surface[1], strategy={"kind": "existing_profile"})
        # No grants, permission flags, or profile copies are introduced here.
        return self.computer.tool("browser_prepare", args)

    def call(self, operation, *, target_id, tab_id, **arguments):
        self._check()
        if operation not in OPERATIONS:
            raise ComputerError("invalid_arguments", "Use state, navigate, click, type, pointer, or dialog.")
        if not isinstance(target_id, str) or not target_id or not isinstance(tab_id, str) or not tab_id:
            raise ComputerError("browser_tab_required", "Use target_id and tab_id returned by this browser's bind/state.")
        if any(k in arguments for k in ("session", "pid", "window_id", "target", "scope", "activate", "bring_to_front")):
            raise ComputerError("invalid_arguments", "Browser actions stay on this exact tab/session; activation and window fallback are unavailable.")
        args = {**arguments, "target_id": target_id, "tab_id": tab_id, "session": self.session}
        return self.computer.tool(OPERATIONS[operation], args)

    def close(self):
        if not self._closed:
            self.computer.tool("end_session", {"session": self.session})
            self.computer._sessions.discard(self.session)
            self._closed = True


def browser_report(browser, result):
    raw = structured(result)
    return {"runtime_version": VERSION, "browser_id": browser.id, "state": raw,
            "input_scope": "exact_browser_tab", "native_window_fallback": False,
            "native_window_tools_available": True,
            "cursor": {"phase": "not_projected", "reason": "Hidden tab coordinates have no proven position in the visible native window."},
            "next_step": ("This refusal concerns the tab/CDP route only. Native Cua window tools remain available: observe the exact window and use AX or screenshot coordinates if the requested page is currently displayed there. This does not provide access to hidden tabs. Do not overwrite a user's tab or change focus to recover."
                          if raw.get("status") == "refused" or raw.get("refusal")
                          else "Use returned target_id/tab_id with this browser_id and observe that tab after input. If setup returned only a new pid/window_id, bind that prepared window first.")}
