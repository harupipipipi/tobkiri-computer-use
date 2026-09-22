#!/usr/bin/env python3
"""Offline structural verifier for the bounded macOS cursor-arrival patch."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "artifacts" / "cua-source"
PATCH = Path(__file__).with_name("0004-macos-bounded-cursor-arrival.patch")
OVERLAY = (
    "libs/cua-driver/rust/crates/platform-macos/src/cursor/overlay.rs"
)
TOOLS = "libs/cua-driver/rust/crates/platform-macos/src/tools"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def source_text(relative: str) -> str:
    return (SOURCE / relative).read_text(encoding="utf-8")


def main() -> int:
    require(SOURCE.is_dir(), f"missing pinned source tree: {SOURCE}")
    require(PATCH.is_file(), f"missing patch: {PATCH}")

    applied = subprocess.run(
        ["git", "-C", str(SOURCE), "apply", "--check", str(PATCH)],
        text=True,
        capture_output=True,
    )
    require(
        applied.returncode == 0,
        f"patch does not apply cleanly:\n{applied.stderr.strip()}",
    )

    patch = PATCH.read_text(encoding="utf-8")
    required_patch_markers = (
        "const CURSOR_ARRIVAL_TIMEOUT: Duration = Duration::from_secs(15);",
        "TrySendError::Full",
        "TrySendError::Disconnected",
        "tokio::time::timeout(CURSOR_ARRIVAL_TIMEOUT, rx)",
        "fn arrival_cancel(key: &CursorKey, id: u64)",
        "superseded_waiter_is_cancelled_without_erasing_the_new_waiter",
        "same_point_one_millisecond_glide_signals_arrival",
        "bounded_enqueue_refuses_unavailable_and_full_queue",
        "cursor_animation_unavailable",
        '"effect": "refused"',
    )
    for marker in required_patch_markers:
        require(marker in patch, f"missing patch marker: {marker}")
    require(
        "old.tx.send" not in patch,
        "superseded waiter must be dropped, not reported as an arrival",
    )

    forbidden = (
        "activateIgnoringOtherApps",
        "CGWarpMouseCursorPosition",
        "CGEventPost",
        "CGEventTapCreate",
    )
    for marker in forbidden:
        require(marker not in patch, f"patch must not add native takeover: {marker}")

    original_overlay = source_text(OVERLAY)
    require(
        "let _ = tx.try_send(OverlayMsg::Cmd(KeyedOverlayCommand { key, cmd }));"
        in original_overlay,
        "unexpected baseline: ignored overlay queue send not found",
    )
    require(
        "let _ = rx.await;" in original_overlay,
        "unexpected baseline: unbounded arrival wait not found",
    )

    animation_callers = {
        "click.rs": 4,
        "double_click.rs": 1,
        "drag.rs": 1,
        "move_cursor.rs": 1,
        "right_click.rs": 1,
        "scroll.rs": 1,
        "set_value.rs": 1,
        "type_text.rs": 1,
    }
    for filename in animation_callers:
        delta = patch.count(f"+++ b/{TOOLS}/{filename}")
        require(delta == 1, f"missing caller update: {filename}")
    returns = patch.count("return super::cursor_animation_refusal(error);")
    require(returns == sum(animation_callers.values()), "not all input callers refuse")

    require(
        "Cursor animation failed before page click dispatch" in patch,
        "page click must reject before JavaScript dispatch",
    )
    require(
        "browser cursor visualization did not arrive" in patch,
        "browser visualization must handle the Result signature",
    )

    print("bounded cursor-arrival patch: offline checks passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError) as error:
        print(f"bounded cursor-arrival patch: FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
