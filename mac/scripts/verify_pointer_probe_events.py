"""Run read-only, in-memory NSEvent getter and PointerProbe type-guard checks."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
REPORT = ROOT / "artifacts" / "pointer-event-getter-reproducer.json"
GETTERS = ("button_number", "click_count", "scrolling_delta_x", "scrolling_delta_y", "precise_scroll", "phase")


def run(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, text=True, capture_output=True)
    result: dict[str, object] = {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if completed.returncode == 0:
        result["json"] = json.loads(completed.stdout)
    return result


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="pointer-probe-", dir=ROOT / "artifacts") as tmp:
        temporary = Path(tmp)
        getters = temporary / "pointer-event-getters"
        validation = temporary / "pointer-probe-nongui-validation"
        library = temporary / "PointerProbeLibrary.swift"
        subprocess.run([
            "swiftc", str(FIXTURES / "PointerEventGetterReproducer.swift"),
            "-framework", "Cocoa", "-o", str(getters),
        ], check=True)
        getter_results = {getter: run([str(getters), getter]) for getter in GETTERS}
        probe_source = (FIXTURES / "PointerProbe.swift").read_text()
        library.write_text(probe_source[:probe_source.index("\nlet app = NSApplication.shared")])
        subprocess.run([
            "swiftc", str(library), str(FIXTURES / "PointerProbeNonGUIValidation.swift"),
            "-framework", "Cocoa", "-framework", "WebKit", "-o", str(validation),
        ], check=True)
        validation_result = run([str(validation)])

    report = {
        "purpose": "In-memory getter probe only; no NSApplication, window, or event posting.",
        "event": "NSEvent.mouseEvent(leftMouseDown)",
        "legacy_getter_subprocesses": getter_results,
        "legacy_getters_rejected_by_appkit": [
            getter for getter, result in getter_results.items() if result["returncode"] != 0
        ],
        "typed_logger_and_counter_validation": validation_result,
    }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if validation_result["returncode"] != 0:
        raise SystemExit("typed validation failed; see " + str(REPORT))
    print(REPORT)


if __name__ == "__main__":
    main()
