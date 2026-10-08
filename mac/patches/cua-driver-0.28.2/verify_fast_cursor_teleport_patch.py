#!/usr/bin/env python3
"""Offline verification for 0013; no daemon, AppKit window, or input dispatch."""

from pathlib import Path
import shutil
import subprocess
import tempfile


PINNED_COMMIT = "fc188250b4ca8549b8e61f937fdb1fb560770e86"
PLATFORM = Path("libs/cua-driver/rust/crates/platform-macos/src")
SERIES = [
    "0001-macos-exact-window-background-drag.patch",
    "0002-macos-drag-always-releases-after-mousedown.patch",
    "0002-macos-exact-ax-window-union.patch",
    "0004-macos-bounded-cursor-arrival.patch",
    "0005-macos-drag-single-pid-route.patch",
    "0006-macos-off-space-exact-ax-window-cache.patch",
    "0007-macos-pointer-single-pid-route.patch",
    "0008-macos-standalone-right-click-focus-guard.patch",
    "0010-macos-ax-top-level-read-diagnostics.patch",
    "0011-macos-pixel-hit-test-axpress-eligibility.patch",
    "0012-macos-window-frame-required-mutations.patch",
    "0013-macos-fast-cursor-teleport.patch",
]


def require(condition, message):
    if not condition:
        raise SystemExit(f"verification failed: {message}")


def main():
    patch_dir = Path(__file__).resolve().parent
    upstream = patch_dir.parents[1] / "artifacts/cua-source"
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=upstream,
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    require(revision == PINNED_COMMIT, f"unexpected upstream revision {revision}")

    with tempfile.TemporaryDirectory(prefix="tobkiri-cursor-teleport-") as tmp:
        checkout = Path(tmp)
        staged = checkout / PLATFORM
        staged.parent.mkdir(parents=True)
        shutil.copytree(upstream / PLATFORM, staged)
        for name in SERIES:
            patch = patch_dir / name
            subprocess.run(["git", "apply", "--check", str(patch)], cwd=checkout, check=True)
            subprocess.run(["git", "apply", str(patch)], cwd=checkout, check=True)

        source_path = staged / "cursor/overlay.rs"
        subprocess.run(
            ["rustfmt", "+stable", "--edition", "2021", "--check", str(source_path)],
            check=True,
        )
        source = source_path.read_text()
        animate = source[source.index("pub async fn animate_cursor_to("):]
        require(
            animate.index("enqueue_teleport(") < animate.index("seed_start_if_sentinel(&key")
            < animate.index("tokio::time::timeout(CURSOR_ARRIVAL_TIMEOUT, rx).await"),
            "teleport must return before seeding, animation, and render-arrival waiting",
        )
        require(
            "current_motion(&key)" in animate and "arrival_supersede(&key);" in animate,
            "fast policy must belong to this session and cancel its older waiter",
        )
        teleport = source[source.index("fn enqueue_teleport("):source.index("/// Convenience for callsites")]
        require("cursor_overlay::track_pointer_command(x, y)" in teleport,
                "teleport must preserve the existing cursor-tip offset")
        require("enqueue_cursor_command(" in teleport and ".await" not in teleport,
                "teleport must use bounded queue acceptance without waiting for rendering")
        require(source.count("forget_requested_motion(&key);") == 2,
                "session removal and revival must both clear requested motion")

        patch = (patch_dir / SERIES[-1]).read_text()
        require(patch.count("+++ b/") == 1 and f"+++ b/{PLATFORM}/cursor/overlay.rs" in patch,
                "teleport patch must change only the overlay, preserving all tool schemas and input routes")
        for forbidden in ("CGEventPost", "CGWarpMouseCursorPosition", "activateIgnoringOtherApps",
                          "delivery_mode", "skip_window_change_detection"):
            require(forbidden not in patch, f"teleport patch must not add {forbidden}")
        for test in (
            "teleport_enqueue_returns_before_any_render_tick",
            "teleport_queue_errors_refuse_without_retrying_or_claiming_arrival",
            "teleport_tip_coordinates_and_repeated_points_need_no_path_or_spring",
            "teleport_replaces_one_cursors_curve_without_touching_another_or_reviving_ended_keys",
            "teleport_policy_is_available_before_render_and_failed_motion_updates_do_not_change_it",
            "teleport_supersedes_only_its_own_waiter_without_false_success",
        ):
            require(f"fn {test}(" in source, f"missing native regression test {test}")

    print("Fast cursor teleport patch: pinned series, formatting, dispatch order, queue failures, and input isolation verified.")


if __name__ == "__main__":
    main()
