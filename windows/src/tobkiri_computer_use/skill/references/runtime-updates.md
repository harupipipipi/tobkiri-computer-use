## Runtime updates without restarting Codex

After installing and testing a completed update, run
`tobkiri-computer-use-reload` from this package's Python environment. Connected
0.1.6+ MCP supervisors replace their idle worker before the next request, keeping
the client connection alive. An in-flight input completes before replacement.
Read `tobkiri_runtime(action="status")` for the loaded version and generation;
`action="reload"` reloads only that connection. Neither route changes grants.

Reload discards observations, browser bindings and owned cursor sessions. If an
action returns `runtime_reloaded`, it was not sent: observe again. Never repeat
an input whose result was timeout/unknown. An uncertain worker is not reloaded
automatically. New helpers can be discovered with `tobkiri_tools(name=...)` and
called through `tobkiri_call(name=..., arguments=...)` if the host caches old tools.
Legacy 0.1.5 connections need one MCP-only reconnect to adopt the supervisor;
do not tell users to restart the entire Codex app for subsequent updates.
If the driver explicitly says its session has ended and rejected a call, an
explicit runtime reload opens a fresh connection; Python should close and open
`Computer` again. Reobserve before continuing. This is distinct from a timeout
or an input whose outcome is unknown; do not replay those inputs.

