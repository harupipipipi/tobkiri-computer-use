# Component-specific window frame mutations (0012)

`0012-macos-window-frame-required-mutations.patch` applies after the frozen
production series `0001`, both `0002` patches, `0004`–`0008`, `0010`, and
`0011`. Experimental patches `0003` and `0009` are excluded.

The upstream `set_window_frame` path required both `AXPosition` and `AXSize` to
be settable and wrote both attributes for every request. A fixed-size window
therefore rejected a position-only move even when its requested size exactly
matched the current WindowServer bounds.

0012 compares the requested frame with the fresh WindowServer frame using the
existing two-point settlement tolerance, then preflights and initially writes
only the components which differ:

- a pure move requires and writes `AXPosition` only;
- a pure resize requires and writes `AXSize` only;
- a mixed change preserves the existing `AXPosition` then `AXSize` order;
- a no-op requires neither attribute and performs zero AX writes.

The settlement loop retains the existing Tahoe rollback correction. If either
component later differs from the requested full frame, it can still be
corrected even when that component matched initially. Every correction checks
the relevant attribute immediately before writing it. A newly non-settable
attribute is not written; the error is recorded and the final WindowServer
readback determines whether the result is confirmed, partial, or unverifiable.

Exact WindowServer owner and AX window-ID matching are unchanged. Confirmation
still comes from WindowServer rather than the AX values that were written.

Run the bounded source verifier without Cargo or GUI access:

```bash
python3 patches/cua-driver-0.28.2/verify_window_frame_required_mutations_patch.py
```

The verifier applies the exact production patch series to a temporary copy,
checks rustfmt and mutation wiring, and runs five isolated Rust tests covering
fixed-size movement, unsupported resize, zero-write no-op, mixed ordering, and
correction of a component that matched initially.
