#!/usr/bin/env python3
"""Offline verification for 0011 after the frozen production series."""

from __future__ import annotations

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
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"verification failed: {message}")


def apply(checkout: Path, patch: Path) -> None:
    checked = subprocess.run(
        ["git", "apply", "--check", str(patch)],
        cwd=checkout,
        text=True,
        capture_output=True,
        check=False,
    )
    require(checked.returncode == 0, checked.stdout + checked.stderr)
    subprocess.run(["git", "apply", str(patch)], cwd=checkout, check=True)


def section(text: str, start: str, end: str) -> str:
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
    require(
        not any(name.startswith("0003-") or name.startswith("0009-") for name in SERIES),
        "experimental 0003/0009 must not enter the production series",
    )

    with tempfile.TemporaryDirectory(prefix="tobkiri-hit-test-axpress-") as tmp:
        checkout = Path(tmp)
        staged = checkout / PLATFORM
        staged.parent.mkdir(parents=True)
        shutil.copytree(upstream / PLATFORM, staged)
        for name in SERIES:
            apply(checkout, patch_dir / name)

        click_path = staged / "tools/click.rs"
        formatted = subprocess.run(
            ["rustfmt", "+stable", "--edition", "2021", "--check", str(click_path)],
            text=True,
            capture_output=True,
            check=False,
        )
        require(
            formatted.returncode == 0,
            "0011 click.rs is not rustfmt-clean:\n" + formatted.stdout + formatted.stderr,
        )

        click = click_path.read_text()
        eligibility = section(
            click,
            "fn hit_test_ax_press_eligible(",
            "/// Return the prior foreground pid",
        )
        shortcut = section(
            click,
            "let delivered = if focus_only {",
            "CFRelease(element as _);",
        )
        require(
            'copy_action_names(element)' in shortcut
            and 'copy_bool_attr(element, "AXEnabled")' in shortcut
            and "hit_test_ax_press_eligible(&advertised, enabled)" in shortcut,
            "live actions/enabled eligibility is not wired into the hit-test shortcut",
        )
        require(
            shortcut.index("hit_test_ax_press_eligible")
            < shortcut.index("AXUIElementPerformAction"),
            "AXPress can be sent before eligibility is proven",
        )
        require(
            "AXRole" not in eligibility and "role" not in eligibility.lower(),
            "0011 introduced a role whitelist",
        )
        require(
            "focus_element(element as usize).is_ok()" in shortcut,
            "focus-only behavior changed",
        )

        tests = section(
            click,
            "#[cfg(test)]\nmod hit_test_ax_press_tests",
            "#[cfg(test)]\nmod selection_fallback_tests",
        )
        harness = checkout / "hit_test_axpress.rs"
        harness.write_text(eligibility + "\n" + tests)
        executable = checkout / "hit-test-axpress-tests"
        subprocess.run(
            ["rustc", "+stable", "--edition=2021", "--test", str(harness), "-o", str(executable)],
            check=True,
        )
        subprocess.run([str(executable)], check=True)

    added = "\n".join(
        line[1:]
        for line in (patch_dir / SERIES[-1]).read_text().splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    for forbidden in ("activate_without_raise", "CGEventPost", "AXRole"):
        require(forbidden not in added, f"0011 adds forbidden behavior: {forbidden}")

    print("Cua 0.28.2 pixel hit-test AXPress eligibility patch verified offline")


if __name__ == "__main__":
    main()
