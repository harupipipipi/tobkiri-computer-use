# Cua Driver 0.28.2 exact AX patches

These patches target only Cua commit `fc188250b4ca8549b8e61f937fdb1fb560770e86`
(`cua-driver-rs-v0.28.2`). They are source artifacts: they do not alter the
installed driver, Accessibility permissions, or desktop state.

## Default patch

Apply [0002-macos-exact-ax-window-union.patch](0002-macos-exact-ax-window-union.patch)
after the existing background-drag patch if that patch is selected for the
build. It brings the mutation gate's top-level AX candidates into agreement
with the observation walker's `AXChildren` plus `AXWindows` union.

Every candidate still requires all of the following:

- an `AXWindow` child where the source is `AXChildren`;
- an exact `_AXUIElementGetWindow` CGWindowID;
- matching WindowServer ownership for the requested PID and window ID.

No title, geometry, focus, foregrounding, Space change, or action retry is
introduced. Duplicate AX proxies are merged by the exact CGWindowID. A known
minimized state is retained across a simple unreadable duplicate. Conflicting
known minimized states set a sticky conflict flag and leave the state unknown,
so a third proxy cannot make the target appear safe through enumeration order.

## Experimental timeout patch

[0003-macos-ax-action-timeout.patch](0003-macos-ax-action-timeout.patch) is
**experimental and excluded from the default build**. Its five-second action
messaging timeout is a diagnostic hypothesis about cached descendants inheriting
the two-second observation budget. It performs one `AXUIElementPerformAction`
call and never retries. Apply it only for a signed native acceptance run that
checks both the requested outcome and the absence of a duplicated effect.

## Verify

Run this from the Tobkiri checkout:

```bash
python3 patches/cua-driver-0.28.2/verify_ax_patches.py
```

The verifier checks the pinned revision, verifies clean application of both
patches without applying them to the source checkout, and uses
`rustc +stable --test` on a temporary pure-Rust model of the merge rule. It
does not invoke native AX APIs or desktop input.

For a default candidate, apply only the selected baseline patch(es) and
`0002`, then run the normal focused Rust/build and signed native acceptance
in the upstream build environment.
