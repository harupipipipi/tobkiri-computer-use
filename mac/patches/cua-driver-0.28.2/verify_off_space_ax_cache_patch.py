#!/usr/bin/env python3
"""Offline verification for patch 0006's exact off-Space AX resolver."""

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
    completed = subprocess.run(
        ["git", "apply", "--check", str(patch)],
        cwd=checkout,
        text=True,
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0, completed.stdout + completed.stderr)
    subprocess.run(["git", "apply", str(patch)], cwd=checkout, check=True)


def main() -> None:
    patch_dir = Path(__file__).resolve().parent
    project_root = patch_dir.parents[1]
    source_root = project_root / "artifacts" / "cua-source"
    union_patch = patch_dir / "0002-macos-exact-ax-window-union.patch"
    cache_patch = patch_dir / "0006-macos-off-space-exact-ax-window-cache.patch"

    with tempfile.TemporaryDirectory(prefix="tobkiri-off-space-ax-") as tmp:
        checkout = Path(tmp)
        destination = checkout / AX_ROOT
        destination.parent.mkdir(parents=True)
        shutil.copytree(source_root / AX_ROOT, destination)
        apply(checkout, union_patch)
        apply(checkout, cache_patch)

        modified = [
            destination / name
            for name in (
                "bindings.rs",
                "exact_target.rs",
                "exact_window_cache.rs",
                "mod.rs",
                "tree.rs",
            )
        ]
        formatted = subprocess.run(
            ["rustfmt", "+stable", "--edition", "2021", "--check", *map(str, modified)],
            text=True,
            capture_output=True,
            check=False,
        )
        require(
            formatted.returncode == 0,
            "patched AX sources are not rustfmt-clean:\n"
            + formatted.stdout
            + formatted.stderr,
        )

        resolver = (destination / "exact_window_cache.rs").read_text()
        tree = (destination / "tree.rs").read_text()
        target = (destination / "exact_target.rs").read_text()

        for marker in (
            "AXUIElementGetPid",
            "ax_get_window_id",
            'copy_string_attr(element, "AXRole")',
            "window.on_current_space == Some(false)",
            "crate::windows::all_windows()",
            "same_process_lifetime",
            "MAX_RETAINED_WINDOWS",
            '["AXFocusedWindow", "AXMainWindow"]',
        ):
            require(marker in resolver, f"missing exact resolver invariant: {marker}")
        require(
            tree.count("resolve_exact_window_fallback") == 1
            and target.count("resolve_exact_window_fallback") == 1,
            "snapshot and mutation validation must use the same exact fallback resolver",
        )
        require(
            "remember_exact_window" in tree and "remember_exact_window" in target,
            "fresh exact snapshot and mutation resolutions must seed the shared cache",
        )
        require(
            "window_info_by_id" not in resolver,
            "fallback must use the layer-0 enumeration carrying exact Space metadata",
        )
        added = "\n".join(
            line[1:]
            for line in cache_patch.read_text().splitlines()
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

        facts_start = resolver.index("#[derive(Debug, Clone, Copy)]\nstruct CachedWindowFacts")
        facts_end = resolver.index("unsafe fn native_identity", facts_start)
        tests_start = resolver.index("#[cfg(test)]\nmod tests")
        harness = checkout / "off_space_admission.rs"
        harness.write_text(
            resolver[facts_start:facts_end] + "\n" + resolver[tests_start:]
        )
        executable = checkout / "off-space-admission-tests"
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

    print("Cua 0.28.2 exact off-Space AX resolver patch verified offline")


if __name__ == "__main__":
    main()
