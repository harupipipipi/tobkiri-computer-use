"""Build the isolated AppKit/WKWebView pointer-delivery fixture without launching it."""
import argparse
from pathlib import Path
import plistlib
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NAME = "TobkiriPointerProbeFixture"
SAFE_NAMES = (DEFAULT_NAME, "TobkiriPointerSafeFixture", "TobkiriPointerTypedFixture")
SOURCE = ROOT / "tests" / "fixtures" / "PointerProbe.swift"
HTML = ROOT / "tests" / "fixtures" / "pointer-probe.html"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", choices=SAFE_NAMES, default=DEFAULT_NAME,
                        help="Select the isolated pointer fixture bundle name")
    args = parser.parse_args()
    name = args.name
    app = ROOT / "artifacts" / f"{name}.app"
    macos = app / "Contents" / "MacOS"
    resources = app / "Contents" / "Resources"
    macos.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleExecutable": name,
        "CFBundleIdentifier": "local.tobkiri." + name.lower(),
        "CFBundleName": name,
        "CFBundlePackageType": "APPL",
        "NSHighResolutionCapable": True,
    }))
    shutil.copy2(HTML, resources / HTML.name)
    subprocess.run([
        "swiftc", str(SOURCE), "-framework", "Cocoa", "-framework", "WebKit",
        "-o", str(macos / name),
    ], check=True)
    print(app)


if __name__ == "__main__":
    main()
