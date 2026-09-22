#!/usr/bin/env python3
"""Verify Cua Driver 0.28.2 exact-AX patches without native AX I/O.

The verifier checks application against the pinned upstream revision and
compiles a temporary harness extracted from the patched production merge helper
and its production tests. It never opens an application, invokes AX APIs, or
sends desktop input.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile


PINNED = "fc188250b4ca8549b8e61f937fdb1fb560770e86"
RELATIVE_EXACT_TARGET = Path(
    "libs/cua-driver/rust/crates/platform-macos/src/ax/exact_target.rs"
)
PATCH_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PATCH_DIR.parents[1]
SOURCE = PROJECT_ROOT / "artifacts" / "cua-source"
UNION_PATCH = PATCH_DIR / "0002-macos-exact-ax-window-union.patch"
TIMEOUT_PATCH = PATCH_DIR / "0003-macos-ax-action-timeout.patch"


def run(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(args)}\n"
            f"{completed.stdout}{completed.stderr}"
        )
    return completed.stdout


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: missing {needle!r}")


def reject(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise AssertionError(f"{label}: forbidden {needle!r}")


def extract_braced_item(text: str, marker: str) -> str:
    start = text.index(marker)
    opening = text.index("{", start)
    depth = 0
    for offset in range(opening, len(text)):
        if text[offset] == "{":
            depth += 1
        elif text[offset] == "}":
            depth -= 1
            if depth == 0:
                return text[start : offset + 1]
    raise AssertionError(f"unclosed item: {marker}")


def extract_test(text: str, name: str) -> str:
    function = f"    fn {name}"
    function_start = text.index(function)
    attribute_start = text.rfind("    #[test]", 0, function_start)
    if attribute_start < 0:
        raise AssertionError(f"test attribute missing: {name}")
    return extract_braced_item(text, text[attribute_start:function_start] + function)


def production_merge_harness(patched: str) -> str:
    record = extract_braced_item(patched, "struct AxWindowRecord")
    merge = extract_braced_item(patched, "fn merge_ax_window_record")
    helper = extract_braced_item(patched, "    fn ax_window(")
    tests = "\n\n".join(
        extract_test(patched, name)
        for name in (
            "top_level_sources_are_unioned_by_exact_window_id()",
            "duplicate_exact_window_id_does_not_create_keyboard_ambiguity()",
            "conflicting_proxy_visibility_fails_closed()",
            "unreadable_duplicate_preserves_known_visibility_regardless_of_order()",
            "conflicting_visibility_is_sticky_across_triple_duplicate_permutations()",
        )
    )
    return (
        f"{record}\n\n{merge}\n\n"
        "#[cfg(test)]\n"
        "mod tests {\n"
        "    use super::{merge_ax_window_record, AxWindowRecord};\n\n"
        f"{helper}\n\n{tests}\n"
        "}\n"
    )


def validate_patch_text() -> None:
    union = UNION_PATCH.read_text()
    for marker in (
        "copy_children(app)",
        "copy_ax_windows(app)",
        'Some("AXWindow")',
        "ax_get_window_id(window)",
        "minimized_conflict: bool",
        "unreadable_duplicate_preserves_known_visibility_regardless_of_order",
        "conflicting_visibility_is_sticky_across_triple_duplicate_permutations",
        "[Some(false), Some(true), Some(false)]",
    ):
        require(union, marker, "union patch")
    for forbidden in ("title fallback", "geometry fallback", "bring_to_front"):
        reject(union.lower(), forbidden, "union patch")

    timeout = TIMEOUT_PATCH.read_text()
    for marker in (
        "EXPERIMENTAL",
        "do not apply this patch by default",
        "unvalidated diagnostic hypothesis",
        "AX_ACTION_MESSAGING_TIMEOUT_SECONDS: f32 = 5.0",
        "AXUIElementSetMessagingTimeout",
        "AXUIElementPerformAction(element, action.as_concrete_TypeRef())",
        "does not retry",
        "unknown",
        "completion state",
    ):
        require(timeout, marker, "timeout patch")
    for forbidden in ("for _ in", "while "):
        reject(timeout, forbidden, "timeout patch")
    if timeout.count("AXUIElementPerformAction(element, action.as_concrete_TypeRef())") != 1:
        raise AssertionError("timeout patch must contain one action invocation")


def main() -> None:
    revision = run("git", "rev-parse", "HEAD", cwd=SOURCE).strip()
    if revision != PINNED:
        raise AssertionError(f"unexpected Cua source revision: {revision}")
    run("git", "apply", "--check", str(UNION_PATCH), cwd=SOURCE)
    run("git", "apply", "--check", str(TIMEOUT_PATCH), cwd=SOURCE)
    validate_patch_text()

    with tempfile.TemporaryDirectory(prefix="tobkiri-ax-merge-") as directory:
        temporary = Path(directory)
        checkout = temporary / "checkout"
        source = checkout / RELATIVE_EXACT_TARGET
        source.parent.mkdir(parents=True)
        shutil.copy2(SOURCE / RELATIVE_EXACT_TARGET, source)
        run(
            "patch",
            "--batch",
            "--forward",
            "-p1",
            "-i",
            str(UNION_PATCH),
            cwd=checkout,
        )
        run("rustfmt", "--check", "--edition", "2021", str(source))
        patched = source.read_text()

        harness = temporary / "production_merge_harness.rs"
        binary = temporary / "production_merge_harness"
        harness.write_text(production_merge_harness(patched))
        run(
            "rustc",
            "+stable",
            "--edition",
            "2021",
            "--test",
            str(harness),
            "-o",
            str(binary),
        )
        run(str(binary), "--quiet")

    print("ok: pinned AX patches apply; extracted production merge tests passed")


if __name__ == "__main__":
    main()
