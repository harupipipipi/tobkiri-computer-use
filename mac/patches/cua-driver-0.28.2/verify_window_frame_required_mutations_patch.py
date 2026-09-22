#!/usr/bin/env python3
"""Offline verification for 0012's component-specific window mutation plan."""

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
    "0012-macos-window-frame-required-mutations.patch",
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

    with tempfile.TemporaryDirectory(prefix="tobkiri-window-frame-plan-") as tmp:
        checkout = Path(tmp)
        staged = checkout / PLATFORM
        staged.parent.mkdir(parents=True)
        shutil.copytree(upstream / PLATFORM, staged)
        for name in SERIES:
            apply(checkout, patch_dir / name)

        source_path = staged / "tools/set_window_frame.rs"
        formatted = subprocess.run(
            ["rustfmt", "+stable", "--edition", "2021", "--check", str(source_path)],
            text=True,
            capture_output=True,
            check=False,
        )
        require(
            formatted.returncode == 0,
            "0012 source is not rustfmt-clean:\n" + formatted.stdout + formatted.stderr,
        )
        source = source_path.read_text()
        mutation_body = section(source, "let result = if let Some(target)", "} else {\n            Err(format!(")
        require(
            mutation_body.index("window_server_frame(window_id)")
            < mutation_body.index("is_attribute_settable"),
            "settable checks still run before the current frame and plan are known",
        )
        require(
            "mutation_errors.extend(apply_mutations(planned));" in mutation_body,
            "initial write does not use the component-specific plan",
        )
        require(
            "required_mutations(requested, Frame::from_ax(rect))" in mutation_body,
            "correction no longer restores every requested frame component that drifts",
        )
        require(
            mutation_body.count("is_attribute_settable(target") == 4,
            "required-attribute preflight and correction-time rechecks changed",
        )
        no_op = section(source, "if planned.is_empty()", "let mut mutation_errors")
        require(
            "return Ok(FrameOutcome" in no_op and "changed: false" in no_op,
            "no-op does not return before all AX writes",
        )

        pure = section(source, "#[derive(Clone, Copy, Debug)]\nstruct Frame", "fn window_server_frame(")
        harness = checkout / "window_frame_plan.rs"
        harness.write_text(
            "#![allow(dead_code)]\n"
            "struct SetWindowFrameInput { x: f64, y: f64, width: f64, height: f64 }\n"
            + pure
            + r"""
#[cfg(test)]
mod tests {
    use super::*;

    fn frame() -> Frame {
        Frame { x: 10.0, y: 20.0, width: 800.0, height: 600.0 }
    }

    #[test]
    fn fixed_size_pure_move_needs_only_position() {
        let before = frame();
        let requested = Frame { x: 100.0, y: 120.0, ..before };
        let plan = required_mutations(requested, before);
        assert_eq!(plan, &POSITION_ONLY);
        assert_eq!(unsupported_required_mutation(plan, true, false), None);
    }

    #[test]
    fn unsupported_actual_resize_is_rejected() {
        let before = frame();
        let requested = Frame { width: 900.0, ..before };
        let plan = required_mutations(requested, before);
        assert_eq!(plan, &SIZE_ONLY);
        assert_eq!(unsupported_required_mutation(plan, true, false), Some(FrameMutation::Size));
    }

    #[test]
    fn no_op_has_zero_planned_writes() {
        let value = frame();
        let plan = required_mutations(value, value);
        assert_eq!(plan.len(), 0);
        assert_eq!(unsupported_required_mutation(plan, false, false), None);
    }

    #[test]
    fn mixed_plan_preserves_position_then_size_order() {
        let before = frame();
        let requested = Frame { x: 100.0, width: 900.0, ..before };
        let plan = required_mutations(requested, before);
        assert_eq!(plan, &FRAME_MUTATION_ORDER);
    }

    #[test]
    fn correction_can_restore_a_component_that_matched_initially() {
        let before = frame();
        let requested = Frame { x: 100.0, ..before };
        let observed = Frame { x: 10.0, width: 700.0, ..before };
        assert_eq!(required_mutations(requested, before), &POSITION_ONLY);
        assert_eq!(required_mutations(requested, observed), &FRAME_MUTATION_ORDER);
    }
}
"""
        )
        executable = checkout / "window-frame-plan-tests"
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
    for forbidden in ("activate_without_raise", "CGEventPost", "resolve_window_owner ="):
        require(forbidden not in added, f"0012 adds unrelated primitive: {forbidden}")

    print("Cua 0.28.2 component-specific window frame mutation patch verified offline")


if __name__ == "__main__":
    main()
