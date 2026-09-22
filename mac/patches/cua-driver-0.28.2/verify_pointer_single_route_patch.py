#!/usr/bin/env python3
"""Offline verification for patches 0007 and 0008; performs no GUI input."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile


PINNED_COMMIT = "fc188250b4ca8549b8e61f937fdb1fb560770e86"
PLATFORM = Path("libs/cua-driver/rust/crates/platform-macos/src")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"verification failed: {message}")


def apply(checkout: Path, patch: Path) -> None:
    completed = subprocess.run(
        ["patch", "--batch", "--forward", "-p1", "-i", str(patch)],
        cwd=checkout,
        text=True,
        capture_output=True,
        check=False,
    )
    require(
        completed.returncode == 0,
        f"{patch.name} does not apply cleanly:\n"
        + completed.stdout
        + completed.stderr,
    )


def body(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def main() -> None:
    patch_dir = Path(__file__).resolve().parent
    project_root = patch_dir.parents[1]
    upstream = project_root / "artifacts" / "cua-source"
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=upstream,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    require(revision == PINNED_COMMIT, f"unexpected upstream revision {revision}")

    series = [
        "0001-macos-exact-window-background-drag.patch",
        "0002-macos-drag-always-releases-after-mousedown.patch",
        "0002-macos-exact-ax-window-union.patch",
        "0004-macos-bounded-cursor-arrival.patch",
        "0005-macos-drag-single-pid-route.patch",
        "0006-macos-off-space-exact-ax-window-cache.patch",
        "0007-macos-pointer-single-pid-route.patch",
        "0008-macos-standalone-right-click-focus-guard.patch",
    ]

    with tempfile.TemporaryDirectory(prefix="tobkiri-pointer-route-") as tmp:
        checkout = Path(tmp)
        staged_platform = checkout / PLATFORM
        staged_platform.parent.mkdir(parents=True)
        shutil.copytree(upstream / PLATFORM, staged_platform)
        for name in series:
            apply(checkout, patch_dir / name)

        changed = [
            staged_platform / "input/mouse.rs",
            staged_platform / "tools/click.rs",
            staged_platform / "tools/right_click.rs",
            staged_platform / "tools/scroll.rs",
        ]
        formatted = subprocess.run(
            ["rustfmt", "+stable", "--edition", "2021", "--check", *map(str, changed)],
            text=True,
            capture_output=True,
            check=False,
        )
        require(
            formatted.returncode == 0,
            "patched pointer files are not rustfmt-clean:\n"
            + formatted.stdout
            + formatted.stderr,
        )

        mouse = changed[0].read_text()
        click = changed[1].read_text()
        right = changed[2].read_text()
        scroll = changed[3].read_text()
        interactive = (staged_platform / "input/interactive.rs").read_text()

        require("MousePostMode::Both" not in mouse, "dual mouse mode remains reachable")
        require(
            "crate::input::skylight::post_to_pid(pid as libc::pid_t, event_ptr, false);\n"
            "        event.post_to_pid(pid as libc::pid_t);" not in mouse,
            "direct adjacent private/public pointer posts remain",
        )

        generic = body(
            mouse,
            "pub(super) fn post_mouse_event(",
            "#[allow(clippy::too_many_arguments)]\nfn post_mouse_event_with_mode",
        )
        require(
            "MousePostMode::SkyLightWithPublicFallback" in generic,
            "background interactive dispatcher is not single-route",
        )
        require(
            interactive.count("super::mouse::post_mouse_event(") == 2,
            "interactive pointer/scroll no longer share the reviewed dispatcher",
        )

        right_inner = body(
            mouse,
            "fn right_click_at_xy_inner(",
            "/// Post a mouse event to `pid`.",
        )
        require(
            right_inner.count("delivery.post_mode()") == 3,
            "right-click primer/down/up must all use the selected single route",
        )
        middle_inner = body(
            mouse,
            "fn middle_click_at_xy_inner(",
            "/// Right-click at `(x, y)`",
        )
        require(
            "wid: Option<u32>" in middle_inner
            and middle_inner.count("delivery.post_mode()") == 2,
            "middle-click does not preserve wid and one route for down/up",
        )
        require(
            "if let Some(wid) = window_id" in click
            and "wid, &m," in click
            and "wid,\n        &[]," in right,
            "an exact-window right/middle caller dropped the CGWindowID",
        )

        wheel = body(mouse, "pub fn scroll_wheel_at_xy(", 'extern "C" {')
        require(
            "delivery: WindowClickDelivery" in wheel
            and wheel.count("post_pid_route(") == 1
            and "delivery.post_mode()" in wheel,
            "wheel ticks are not dispatched once through the explicit route",
        )
        require(
            "WindowClickDelivery::from_foreground(fg)" in scroll,
            "scroll tool did not propagate foreground/background delivery",
        )

        require(
            "focus_guard::with_focus_suppressed(" in right
            and '"right_click.pixel"' in right
            and "WindowChangeDetector::snapshot(prior_front)" in right,
            "standalone right-click lacks the shared background focus guard",
        )

        helper_start = mouse.index("#[derive(Clone, Copy)]\nenum MousePostMode")
        helper_end = mouse.index("/// Left-click at `(x, y)`", helper_start)
        tests_start = mouse.index("#[cfg(test)]\nmod single_pid_drag_route_tests")
        harness = checkout / "pointer_single_route.rs"
        harness.write_text(mouse[helper_start:helper_end] + "\n" + mouse[tests_start:])
        executable = checkout / "pointer-single-route-tests"
        subprocess.run(
            [
                "rustc",
                "+stable",
                "--edition=2021",
                "--test",
                str(harness),
                "-o",
                str(executable),
            ],
            check=True,
        )
        subprocess.run([str(executable)], check=True)

    added = "\n".join(
        line[1:]
        for name in series[-2:]
        for line in (patch_dir / name).read_text().splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    for forbidden in ("CGEventTapLocation::HID", "warp_mouse_cursor_position"):
        require(forbidden not in added, f"patch adds forbidden physical input: {forbidden}")

    print("Cua 0.28.2 pointer single-route and right-click focus patches verified offline")


if __name__ == "__main__":
    main()
