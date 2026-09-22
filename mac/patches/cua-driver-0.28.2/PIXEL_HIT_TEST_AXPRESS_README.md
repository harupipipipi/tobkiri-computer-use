# Pixel hit-test AXPress eligibility (0011)

`0011-macos-pixel-hit-test-axpress-eligibility.patch` applies after the frozen
production patches `0001`, both `0002` patches, `0004`–`0008`, and `0010`.
Experimental patches `0003` and `0009` are excluded.

For a background single left pixel click, Cua first resolves the element at the
screen point and proves that it belongs to the exact requested window. Before
0011 it then called `AXUIElementPerformAction(AXPress)` without checking whether
the live element advertised that action. macOS can return success for a hollow
semantic action, causing the tool to return the accessibility route without
ever delivering the requested coordinate click.

0011 permits this AX shortcut only when the live element advertises `AXPress`
and does not report `AXEnabled=false`. Otherwise it sends no AX action and
continues into the existing exact-window pixel path. The focus-only action is
unchanged.

There is deliberately no role whitelist. WebKit, Chromium, AppKit, and custom
controls can expose valid press actions under different roles; the live action
list is the direct capability signal. The patch adds no retry, foreground
switch, schema change, new route, or event dispatch primitive.

This removes a known unsupported-action shortcut. It does not prove that an
advertised AXPress will emit DOM mouse callbacks, and it does not establish the
cause of the earlier WKWebView fixture result.

Run the bounded source verifier without Cargo or GUI access:

```bash
python3 patches/cua-driver-0.28.2/verify_pixel_hit_test_axpress_patch.py
```

The verifier applies the exact production series to a temporary copy, checks
rustfmt and closure ordering, and runs isolated Rust tests for advertised,
missing, enabled, disabled, and unreported-enabled cases.
