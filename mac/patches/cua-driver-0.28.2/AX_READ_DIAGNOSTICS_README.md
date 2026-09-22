# AX top-level read diagnostics (0010)

`0010-macos-ax-top-level-read-diagnostics.patch` applies after the frozen
production series `0001`, both `0002` patches, `0004`–`0008`. Experimental
patches `0003` and `0009` are deliberately excluded.

The upstream macOS paths converted every failed `AXChildren` or `AXWindows`
read into an empty vector. A target application which timed out with
`kAXErrorCannotComplete` (`-25204`) therefore looked like a responsive app
with no matching AX window. Snapshots reported `ax_window_unresolved` and
recommended foreground input, while mutation gates returned the generic
off-Space/unresolved refusal.

0010 retains the native result for each top-level operation and reports a
small diagnostic object:

```json
{
  "code": "ax_application_unresponsive",
  "effect": "refused",
  "ax_read_errors": [
    {"operation": "AXWindows", "code": -25204}
  ],
  "suggestion": "wait for the application to respond, then take a fresh snapshot"
}
```

The new diagnosis is intentionally narrow:

- only `kAXErrorCannotComplete` is classified as application unresponsiveness;
  `kAXErrorAttributeUnsupported`, `kAXErrorNoValue`, a successful empty list,
  and other native errors keep their existing behavior;
- an exact target found by either top-level source or the existing exact-window
  resolver wins even if the other source timed out;
- WindowServer not-found and foreign-owner results remain stronger than an AX
  timeout;
- unresolved mutations still fail closed and send no input;
- the timeout diagnosis recommends waiting and re-snapshotting, with no
  foreground, activation, Space switch, retry, or input fallback.

Snapshot walking and mutation validation still make separate fresh native
reads. The diagnostic says that a top-level query could not complete; it does
not identify why the application stopped answering and does not claim event
delivery success or failure.

Run the bounded verifier without Cargo or GUI access:

```bash
python3 patches/cua-driver-0.28.2/verify_ax_read_diagnostics_patch.py
```

The verifier copies the pinned upstream platform source to a temporary
directory, applies exactly the frozen eight patches plus 0010, checks rustfmt,
checks both snapshot and mutation propagation, and runs three isolated Rust
tests for error classification and diagnosis precedence. Use
`scripts/build_patched_driver.py --resume` with the same ordered nine-patch
series for an actual candidate build; do not build or test the pristine source
directly.
