#!/usr/bin/env python3
"""Offline verification for draft 0009; performs no AX or GUI operations."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile


AX_ROOT = Path("libs/cua-driver/rust/crates/platform-macos/src/ax")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"verification failed: {message}")


def apply(checkout: Path, patch: Path) -> None:
    result = subprocess.run(
        ["git", "apply", "--check", str(patch)],
        cwd=checkout,
        text=True,
        capture_output=True,
        check=False,
    )
    require(result.returncode == 0, result.stdout + result.stderr)
    subprocess.run(["git", "apply", str(patch)], cwd=checkout, check=True)


def main() -> None:
    patch_dir = Path(__file__).resolve().parent
    project_root = patch_dir.parents[1]
    source = project_root / "artifacts" / "cua-source" / AX_ROOT

    with tempfile.TemporaryDirectory(prefix="tobkiri-space-neutral-ax-") as tmp:
        checkout = Path(tmp)
        destination = checkout / AX_ROOT
        destination.parent.mkdir(parents=True)
        shutil.copytree(source, destination)
        for name in (
            "0002-macos-exact-ax-window-union.patch",
            "0006-macos-off-space-exact-ax-window-cache.patch",
            "0009-macos-exact-ax-cache-space-neutral.patch",
        ):
            apply(checkout, patch_dir / name)

        resolver_path = destination / "exact_window_cache.rs"
        formatted = subprocess.run(
            ["rustfmt", "+stable", "--edition", "2021", "--check", str(resolver_path)],
            text=True,
            capture_output=True,
            check=False,
        )
        require(
            formatted.returncode == 0,
            "patched resolver is not rustfmt-clean:\n"
            + formatted.stdout
            + formatted.stderr,
        )

        resolver = resolver_path.read_text()
        for marker in (
            "AXUIElementGetPid",
            "ax_get_window_id",
            'copy_string_attr(element, "AXRole")',
            "same_window_server_owner",
            "same_process_lifetime",
            "process_start_stamp(pid)",
            "MAX_RETAINED_WINDOWS",
            '["AXFocusedWindow", "AXMainWindow"]',
            "crate::windows::all_windows()",
        ):
            require(marker in resolver, f"missing exact identity invariant: {marker}")

        for removed_gate in (
            "explicitly_off_space",
            "window_server_reports_exact_off_space_owner",
            "window.on_current_space == Some(false)",
        ):
            require(
                removed_gate not in resolver,
                f"Space membership still gates exact cache reuse: {removed_gate}",
            )

        require(
            "window.window_id" not in resolver
            or ".map(|window| (window.pid, window.window_id))" in resolver,
            "WindowServer validation must preserve both pid and CGWindowID",
        )
        require(
            resolver.count("window_server_reports_exact_owner(pid, window_id)") == 2,
            "focused/main and retained-cache paths must share exact owner validation",
        )

        facts_start = resolver.index("#[derive(Debug, Clone, Copy)]\nstruct CachedWindowFacts")
        facts_end = resolver.index("unsafe fn native_identity", facts_start)
        owner_start = resolver.index("fn exact_owner_in_rows(")
        owner_end = resolver.index("fn window_server_reports_exact_owner", owner_start)
        tests_start = resolver.index("#[cfg(test)]\nmod tests")
        harness = checkout / "space_neutral_admission.rs"
        harness.write_text(
            resolver[facts_start:facts_end]
            + "\n"
            + resolver[owner_start:owner_end]
            + "\n"
            + resolver[tests_start:]
        )
        executable = checkout / "space-neutral-admission-tests"
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
        for line in (patch_dir / "0009-macos-exact-ax-cache-space-neutral.patch")
        .read_text()
        .splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    for forbidden in (
        "AXTitle",
        "window_bounds",
        "activate_pid",
        "activate_without_raise",
        "warp_mouse_cursor_position",
        "switch_space",
    ):
        require(forbidden not in added, f"forbidden fallback primitive: {forbidden}")

    print("draft 0009 space-neutral exact AX cache verified offline")


if __name__ == "__main__":
    main()
