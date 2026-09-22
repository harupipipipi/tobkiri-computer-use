#!/usr/bin/env python3
"""Offline integrity and invariant checks for the Cua 0.28.2 drag patch."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile


EXPECTED_SOURCE_SHA256 = (
    "3f65ed593d883560a0079e027aa397858e905089f2003fd3bf16ccc35752d6f7"
)
EXPECTED_MOUSE_SHA256 = (
    "271fff5e387db4808fe7af0d38ddb6c8b27e96f1dfe2a1c524e5dc1786707aee"
)
RELATIVE_SOURCE = Path(
    "libs/cua-driver/rust/crates/platform-macos/src/tools/drag.rs"
)
RELATIVE_MOUSE = Path(
    "libs/cua-driver/rust/crates/platform-macos/src/input/mouse.rs"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"verification failed: {message}")


def main() -> None:
    patch_dir = Path(__file__).resolve().parent
    project_root = patch_dir.parents[1]
    source_root = project_root / "artifacts" / "cua-source"
    source = source_root / RELATIVE_SOURCE
    mouse_source = source_root / RELATIVE_MOUSE
    patch = patch_dir / "0001-macos-exact-window-background-drag.patch"
    release_patch = patch_dir / "0002-macos-drag-always-releases-after-mousedown.patch"
    patch_text = patch.read_text()
    release_patch_text = release_patch.read_text()

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    require(
        digest == EXPECTED_SOURCE_SHA256,
        f"unexpected upstream drag.rs SHA-256 {digest}",
    )
    mouse_digest = hashlib.sha256(mouse_source.read_bytes()).hexdigest()
    require(
        mouse_digest == EXPECTED_MOUSE_SHA256,
        f"unexpected upstream mouse.rs SHA-256 {mouse_digest}",
    )

    with tempfile.TemporaryDirectory(prefix="tobkiri-drag-patch-") as tmp:
        checkout = Path(tmp)
        staged_source = checkout / RELATIVE_SOURCE
        staged_source.parent.mkdir(parents=True)
        shutil.copy2(source, staged_source)
        staged_mouse = checkout / RELATIVE_MOUSE
        staged_mouse.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mouse_source, staged_mouse)
        for candidate in (patch, release_patch):
            completed = subprocess.run(
                ["patch", "--batch", "--forward", "-p1", "-i", str(candidate)],
                cwd=checkout,
                text=True,
                capture_output=True,
                check=False,
            )
            require(
                completed.returncode == 0,
                f"{candidate.name} does not apply cleanly:\n"
                + completed.stdout
                + completed.stderr,
            )
        patched = staged_source.read_text()
        patched_mouse = staged_mouse.read_text()
        # Execute the production endpoint predicate and its actual Rust tests,
        # without linking macOS input libraries or building the full workspace.
        predicate = patched[patched.index("fn drag_endpoints_within_window("):patched.index("impl DragTool {")]
        tests = patched[patched.index("#[cfg(test)]"):]
        harness = checkout / "drag_bounds.rs"
        harness.write_text(predicate + "\n" + tests)
        executable = checkout / "drag-bounds-tests"
        subprocess.run(["rustc", "+stable", "--edition=2021", "--test", str(harness),
                        "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)

    require(
        "Background drag is unavailable on macOS" not in patched,
        "legacy unconditional background refusal remains",
    )
    markers = [
        "gate_background_window_action(",
        "BackgroundAction::WindowPointer",
        "&& !drag_endpoints_within_window(",
        "crate::input::mouse::drag_at_xy_observed(",
        "finish_window_observation(snapshot, &args).await",
    ]
    positions = [patched.find(marker) for marker in markers]
    require(all(position >= 0 for position in positions), "required invariant marker missing")
    require(
        positions == sorted(positions),
        "target gate, bounds check, PID dispatch, and observation are out of order",
    )
    require(
        "background_drag_accepts_only_finite_in_frame_endpoints" in patched,
        "deterministic endpoint unit test missing",
    )
    require(
        "let window_id = match super::native_window_id" in patched,
        "window id conversion can truncate rather than refuse",
    )
    require(
        "x < width && y < height" in patched
        and "(640.0, 20.0)" in patched
        and "(20.0, 480.0)" in patched,
        "right/bottom edges are not covered by the exclusive-bounds contract",
    )
    added_lines = "\n".join(
        line[1:]
        for line in patch_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    for forbidden in (
        "activate_pid(",
        "drag_at_xy_foreground_observed(",
        "warp_mouse_cursor_position(",
    ):
        require(
            forbidden not in added_lines,
            f"background capability adds forbidden foreground/HID primitive {forbidden}",
        )
    drag_start = patched_mouse.find("pub fn drag_at_xy_observed")
    drag_end = patched_mouse.find("/// Foreground drag through the global HID event tap.")
    require(drag_start >= 0 and drag_end > drag_start, "PID drag function not found")
    drag_body = patched_mouse[drag_start:drag_end]
    lifecycle_markers = [
        'anyhow!("drag mouseUp failed before mouseDown")',
        "post_mouse_event(\n        pid,\n        &down,",
        "let path_result = (|| -> anyhow::Result<()> {",
        "post_mouse_event(pid, &up,",
        "path_result\n}",
    ]
    lifecycle_positions = [drag_body.find(marker) for marker in lifecycle_markers]
    require(
        all(position >= 0 for position in lifecycle_positions)
        and lifecycle_positions == sorted(lifecycle_positions),
        "mouseUp is not guaranteed after the PID-routed mouseDown",
    )
    release_added_lines = "\n".join(
        line[1:]
        for line in release_patch_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    require(
        "CGEventTapLocation::HID" not in release_added_lines
        and "warp_mouse_cursor_position" not in release_added_lines,
        "release repair adds a HID or hardware-pointer fallback",
    )
    print("Cua 0.28.2 background-drag patch verified offline")


if __name__ == "__main__":
    main()
