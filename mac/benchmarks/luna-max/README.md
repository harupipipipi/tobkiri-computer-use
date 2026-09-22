# Same-prompt Luna Max comparison

## Public templates

`prompt.template.md` and `quality-prompt.template.md` contain the shared task
with the original machine paths replaced by `{{MAC_ROOT}}`. Replace that value
with the absolute path to this checkout's `mac/` directory, then give both
agents exactly the same rendered prompt bytes. Compute and record the SHA-256
of that rendered prompt; it differs from the historical hashes below.

Copy `config.example.json` to `runs/RUN/config.json` for each agent, substitute
the path and run name, and fill in the actual prompt hash and dedicated fixture
app. Set `backend` to `standard` or `tobkiri`. Build separate empty fixtures from
the same source. Run configurations, the original machine-specific prompts,
screenshots and raw logs are local only and excluded from Git.

All paths below are relative to `mac/`. A template or example configuration is
not evidence of a completed run. Results and their limitations are summarized
in [the comparison report](../../docs/LUNA_MAX_COMPARISON.md).

## Historical baseline

Both original runs used `gpt-5.6-luna` with reasoning `max` and the exact bytes of
`prompt.md`. The prompt SHA-256 is
`446602ea674c4c9dd22c6656e36fdf8f711d039de351bb5d94752c471f6a60f5`.
The historical quality prompt SHA-256 is
`4b03ec535772eeb5327a06683d24e3e57ad22ab0838cf2805ed039774250ce1a`.
Only the run configuration changes the assigned backend, empty fixture app,
and output directory. Both fixture apps are built from the same
`tests/fixtures/ComputerFixture.swift` with `--drawing`.

The parent prepares the empty app and audits code; Luna performs all GUI
observation, input, coordinate selection, and verification. Agents do not see
the other run's results or receive drawing/coordinate coaching. Backend
switching, editing canvas data directly, and foreground/hardware fallback are
excluded. Input stops after eight minutes or sixty operations; final reporting
and a pending call's termination can run past that boundary.

Artifacts are under `artifacts/luna-max/<run>/`. The fixture's event log records
actual canvas down/drag/up events, colors, and target active/key status. It does
not record semantic title/button actions or prove hardware-pointer isolation.
An event count is not a count of tool calls.

The independent `judge` pass uses the same read-only Tobkiri screenshot method
for both completed windows. It is separate from the tested agents' performance
and does not repair or complete either drawing. The standard agent's own
screenshots remain in its tool output because its documented surface did not
provide a file-save operation.

This is a single native drawing task, not a broad success-rate estimate.
Cross-Space access, browser tabs, focus retention, multiple cursors and other
capabilities need separate cases. Current results and limitations are in
`docs/LUNA_MAX_COMPARISON.md`.

## Quality-first follow-up

On 2026-09-22 the user clarified that completed results matter more than speed.
`quality-prompt.md` is the common prompt for subsequent quality runs. It keeps
the same drawing requirements, permits observed correction through the actual
UI, and scores completion, correctness and non-interference. Timing is recorded
only as context. The twenty-minute / 120-input bounds stop unproductive or
unbounded trials; they are not a latency target. Both backends receive identical
prompt bytes. Keep the original `prompt.md` and its baseline results unchanged.

A Tobkiri candidate run may specify `computer_command` in its run configuration
to select the already-running, separately permissioned driver. That connection
setting supplies no drawing coordinates or strategy and does not change the
saved default runtime. Native permission/preflight checks must pass before the
drawing run starts. Preparing a run configuration does not mean it has run.
