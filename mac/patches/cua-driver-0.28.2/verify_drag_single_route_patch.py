#!/usr/bin/env python3
"""Offline verification for patch 0005's drag-only single-route policy."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile


UPSTREAM_MOUSE_SHA256 = (
    "271fff5e387db4808fe7af0d38ddb6c8b27e96f1dfe2a1c524e5dc1786707aee"
)
RELATIVE_MOUSE = Path(
    "libs/cua-driver/rust/crates/platform-macos/src/input/mouse.rs"
)


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


def main() -> None:
    patch_dir = Path(__file__).resolve().parent
    project_root = patch_dir.parents[1]
    source = project_root / "artifacts" / "cua-source" / RELATIVE_MOUSE
    release_patch = patch_dir / "0002-macos-drag-always-releases-after-mousedown.patch"
    route_patch = patch_dir / "0005-macos-drag-single-pid-route.patch"

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    require(
        digest == UPSTREAM_MOUSE_SHA256,
        f"unexpected upstream mouse.rs SHA-256 {digest}",
    )

    with tempfile.TemporaryDirectory(prefix="tobkiri-drag-route-") as tmp:
        checkout = Path(tmp)
        staged = checkout / RELATIVE_MOUSE
        staged.parent.mkdir(parents=True)
        shutil.copy2(source, staged)
        apply(checkout, release_patch)
        apply(checkout, route_patch)
        patched = staged.read_text()

        formatted = subprocess.run(
            [
                "rustfmt",
                "+stable",
                "--edition",
                "2021",
                "--check",
                str(staged),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        require(
            formatted.returncode == 0,
            "patched mouse.rs is not rustfmt-clean:\n"
            + formatted.stdout
            + formatted.stderr,
        )

        drag_start = patched.index("pub fn drag_at_xy_observed")
        drag_end = patched.index(
            "/// Foreground drag through the global HID event tap.", drag_start
        )
        drag_body = patched[drag_start:drag_end]
        require(
            drag_body.count("post_drag_mouse_event(") == 3,
            "drag down/path/up must each use the drag-only dispatcher",
        )
        require(
            "post_mouse_event(" not in drag_body,
            "background drag still reaches the dual-route dispatcher",
        )

        dispatcher_start = patched.index("fn post_drag_mouse_event(")
        dispatcher_end = patched.index(
            "#[allow(clippy::too_many_arguments)]\npub(super) fn post_mouse_event",
            dispatcher_start,
        )
        dispatcher = patched[dispatcher_start:dispatcher_end]
        require(
            "MousePostMode::SkyLightWithPublicFallback" in dispatcher,
            "drag dispatcher does not select the single-route policy",
        )

        mode_start = patched.index("MousePostMode::SkyLightWithPublicFallback =>")
        mode_end = patched.index(
            "MousePostMode::PublicOnly =>", mode_start
        )
        mode_body = patched[mode_start:mode_end]
        require(
            "post_single_pid_route(" in mode_body
            and "skylight::post_to_pid" in mode_body
            and "event.post_to_pid" in mode_body,
            "single-route policy does not prefer SkyLight with public fallback",
        )

        helper_start = patched.index(
            "#[derive(Debug, Clone, Copy, PartialEq, Eq)]\nenum SinglePostRoute"
        )
        helper_end = patched.index(
            "#[derive(Clone, Copy)]\npub enum WindowClickDelivery", helper_start
        )
        tests_start = patched.index(
            "#[cfg(test)]\nmod single_pid_drag_route_tests"
        )
        harness = checkout / "drag_single_route.rs"
        harness.write_text(
            patched[helper_start:helper_end]
            + "\n"
            + patched[tests_start:]
        )
        executable = checkout / "drag-single-route-tests"
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
        for line in route_patch.read_text().splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    for forbidden in (
        "CGEventTapLocation::HID",
        "warp_mouse_cursor_position",
        "activate_pid(",
        "activate_without_raise(",
    ):
        require(
            forbidden not in added,
            f"patch adds forbidden foreground/HID primitive {forbidden}",
        )

    print("Cua 0.28.2 drag single-route patch verified offline")


if __name__ == "__main__":
    main()
