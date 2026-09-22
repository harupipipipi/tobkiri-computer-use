"""Build a disposable native UI for repeatable computer-use acceptance tests."""
from pathlib import Path
import argparse
import plistlib
import re
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--name", default="TobkiriFixture")
parser.add_argument("--single", action="store_true")
parser.add_argument("--drawing", action="store_true", help="Open an empty native drawing canvas instead of the control fixture")
parser.add_argument("--pixel-grid", action="store_true", help="Use native clickable cells for the drawing canvas")
args = parser.parse_args()
if not re.fullmatch(r"Tobkiri[A-Za-z]*Fixture", args.name):
    parser.error("Use a Tobkiri...Fixture name")
root = Path(__file__).resolve().parents[1]
app = root / f"artifacts/{args.name}.app"
(app / "Contents/MacOS").mkdir(parents=True, exist_ok=True)
(app / "Contents/Info.plist").write_bytes(plistlib.dumps({
    "CFBundleExecutable": args.name, "CFBundleIdentifier": "local.tobkiri." + args.name.lower(),
    "CFBundleName": args.name, "CFBundlePackageType": "APPL", "NSHighResolutionCapable": True,
    "TobkiriSingleWindow": args.single,
    "TobkiriDrawingMode": args.drawing or args.pixel_grid,
    "TobkiriPixelMode": args.pixel_grid,
}))
subprocess.run(["swiftc", str(root / "tests/fixtures/ComputerFixture.swift"),
                "-o", str(app / f"Contents/MacOS/{args.name}")], check=True)
print(app)
