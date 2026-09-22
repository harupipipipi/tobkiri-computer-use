#!/usr/bin/env python3
"""Offline verification for 0010 after the frozen eight-patch series; no GUI/input."""

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

    with tempfile.TemporaryDirectory(prefix="tobkiri-ax-read-diagnostics-") as tmp:
        checkout = Path(tmp)
        staged = checkout / PLATFORM
        staged.parent.mkdir(parents=True)
        shutil.copytree(upstream / PLATFORM, staged)
        for name in SERIES:
            apply(checkout, patch_dir / name)

        changed = [
            staged / relative
            for relative in (
                "ax/bindings.rs",
                "ax/exact_target.rs",
                "ax/tree.rs",
                "browser/setup_ui.rs",
                "tools/get_window_state.rs",
                "tools/mod.rs",
                "tools/type_text.rs",
            )
        ]
        formatted = subprocess.run(
            ["rustfmt", "+stable", "--edition", "2021", "--check", *map(str, changed)],
            text=True,
            capture_output=True,
            check=False,
        )
        require(
            formatted.returncode == 0,
            "0010 sources are not rustfmt-clean:\n" + formatted.stdout + formatted.stderr,
        )

        bindings = changed[0].read_text()
        exact = changed[1].read_text()
        tree = changed[2].read_text()
        state = changed[4].read_text()
        tools = changed[5].read_text()
        type_text = changed[6].read_text()

        require(
            'copy_element_list_attr(element, "AXChildren")' in bindings
            and 'copy_element_list_attr(element, "AXWindows")' in bindings,
            "top-level reads do not retain operation-specific native errors",
        )
        require(
            tree.count("copy_children_with_error") == 1
            and tree.count("copy_ax_windows_with_error") == 1
            and exact.count("copy_children_with_error") == 2
            and exact.count("copy_ax_windows_with_error") == 2,
            "snapshot and mutation paths do not use detailed top-level reads",
        )
        require(
            "error.is_app_unresponsive().then_some(error)" in tree
            and "error.is_app_unresponsive().then_some(error)" in exact,
            "native error filtering no longer distinguishes CannotComplete",
        )
        require(
            "unresolved_due_to_app_unresponsive(&gathered)" in tools
            and "unresolved_due_to_app_unresponsive(&gathered)" in type_text
            and "unresolved_due_to_app_unresponsive(&gathered)" in state,
            "one mutation/capability gate bypasses the shared diagnosis predicate",
        )
        snapshot_diagnostic = section(
            state,
            "let unresolved_ax_errors =",
            "// Additive read-only `background_input` capability section",
        )
        require(
            "WindowScope::AxUnresolved" in snapshot_diagnostic,
            "snapshot timeout diagnosis can shadow not-found/foreign-owner scope",
        )
        unresponsive_result = section(
            tools,
            "pub(crate) fn ax_application_unresponsive_result(",
            "/// Exclusive per-process ownership",
        )
        require(
            '"operation": error.operation' in tools
            and '"code": error.code' in tools
            and '"code": "ax_application_unresponsive"' in unresponsive_result,
            "structured diagnosis lacks stable code or operation/native-code provenance",
        )
        require(
            "foreground" not in unresponsive_result.lower()
            and "foreground" not in snapshot_diagnostic.lower().split("} else {")[0],
            "unresponsive-app diagnosis must not recommend foreground input",
        )

        error_type = section(
            bindings,
            "#[derive(Debug, Clone, Copy, PartialEq, Eq)]\npub struct AxTopLevelReadError",
            "pub struct AxElementListRead",
        )
        predicate = section(
            exact,
            "pub fn unresolved_due_to_app_unresponsive(",
            "/// Count independently AX-mapped",
        )
        harness = checkout / "ax_read_diagnostics.rs"
        harness.write_text(
            """
#![allow(dead_code, non_upper_case_globals, private_interfaces)]
type AXError = i32;
const kAXErrorCannotComplete: AXError = -25204;
const kAXErrorAttributeUnsupported: AXError = -25205;
const kAXErrorNoValue: AXError = -25212;

#[derive(Clone, Debug)]
enum WindowServerOwnership { SamePid, NotFound, ForeignPid { owner_pid: i32 } }
#[derive(Clone, Debug)]
struct BackgroundTargetFacts { window_server: WindowServerOwnership, ax_window_present: bool }
struct GatheredBackgroundFacts {
    facts: BackgroundTargetFacts,
    ax_read_errors: Vec<AxTopLevelReadError>,
}
"""
            + error_type
            + predicate
            + r"""
#[cfg(test)]
mod tests {
    use super::*;

    fn gathered(owner: WindowServerOwnership, present: bool, code: Option<AXError>) -> GatheredBackgroundFacts {
        GatheredBackgroundFacts {
            facts: BackgroundTargetFacts { window_server: owner, ax_window_present: present },
            ax_read_errors: code.map(|code| AxTopLevelReadError { operation: "AXWindows", code }).into_iter().collect(),
        }
    }

    #[test]
    fn only_cannot_complete_means_unresponsive() {
        assert!(AxTopLevelReadError { operation: "AXChildren", code: kAXErrorCannotComplete }.is_app_unresponsive());
        assert!(!AxTopLevelReadError { operation: "AXChildren", code: kAXErrorAttributeUnsupported }.is_app_unresponsive());
        assert!(!AxTopLevelReadError { operation: "AXChildren", code: kAXErrorNoValue }.is_app_unresponsive());
    }

    #[test]
    fn exact_match_from_other_source_wins() {
        assert!(!unresolved_due_to_app_unresponsive(&gathered(WindowServerOwnership::SamePid, true, Some(kAXErrorCannotComplete))));
    }

    #[test]
    fn timeout_does_not_shadow_window_server_failures_or_normal_empty() {
        assert!(unresolved_due_to_app_unresponsive(&gathered(WindowServerOwnership::SamePid, false, Some(kAXErrorCannotComplete))));
        assert!(!unresolved_due_to_app_unresponsive(&gathered(WindowServerOwnership::SamePid, false, None)));
        assert!(!unresolved_due_to_app_unresponsive(&gathered(WindowServerOwnership::NotFound, false, Some(kAXErrorCannotComplete))));
        assert!(!unresolved_due_to_app_unresponsive(&gathered(WindowServerOwnership::ForeignPid { owner_pid: 9 }, false, Some(kAXErrorCannotComplete))));
    }
}
"""
        )
        executable = checkout / "ax-read-diagnostics-tests"
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
    for forbidden in ("CGEventPost", "warp_mouse_cursor_position", "activate_without_raise"):
        require(forbidden not in added, f"diagnostic patch adds input/focus primitive: {forbidden}")

    print("Cua 0.28.2 AX top-level read diagnostics patch verified offline")


if __name__ == "__main__":
    main()
