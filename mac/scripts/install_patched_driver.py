#!/usr/bin/env python3
"""Install one reviewed patched driver bundle under its stable local identity.

This is intentionally an initial-install primitive, not an updater.  It never
stops a daemon, changes TCC, installs a CLI symlink, or touches CuaDriver.app.
The only supported destination is /Applications/CuaDriverLocal.app, and an
existing path (including a dangling symlink) is a hard refusal.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import tempfile
from typing import Callable, Sequence


DESTINATION = Path("/Applications/CuaDriverLocal.app")
EXPECTED_BUNDLE_ID = "com.trycua.driver.local"
EXPECTED_EXECUTABLE = "cua-driver-local"
CANONICAL_APP_NAME = "Cua Driver Local"
LSREGISTER = Path(
    "/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/"
    "LaunchServices.framework/Versions/A/Support/lsregister"
)
RENAME_EXCL = 0x00000004

Runner = Callable[..., subprocess.CompletedProcess[str]]
Publisher = Callable[[Path, Path], None]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def path_exists_at_all(path: Path) -> bool:
    """Like exists(), but true for dangling symlinks too."""
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def read_bundle_info(app: Path) -> dict:
    info_path = app / "Contents" / "Info.plist"
    try:
        with info_path.open("rb") as stream:
            info = plistlib.load(stream)
    except (OSError, plistlib.InvalidFileException) as exc:
        raise RuntimeError(f"Cannot read bundle plist {info_path}: {exc}") from exc
    if not isinstance(info, dict):
        raise RuntimeError(f"Bundle plist is not a dictionary: {info_path}")
    return info


def validate_bundle_layout(app: Path) -> tuple[dict, Path]:
    if app.is_symlink() or not app.is_dir():
        raise RuntimeError(f"Source must be a real .app directory, not a symlink: {app}")
    info = read_bundle_info(app)
    if info.get("CFBundleIdentifier") != EXPECTED_BUNDLE_ID:
        raise RuntimeError(
            f"Refusing bundle id {info.get('CFBundleIdentifier')!r}; "
            f"expected {EXPECTED_BUNDLE_ID!r}"
        )
    if info.get("CFBundleExecutable") != EXPECTED_EXECUTABLE:
        raise RuntimeError(
            f"Refusing executable {info.get('CFBundleExecutable')!r}; "
            f"expected {EXPECTED_EXECUTABLE!r}"
        )
    executable = app / "Contents" / "MacOS" / EXPECTED_EXECUTABLE
    if executable.is_symlink() or not executable.is_file():
        raise RuntimeError(f"Bundle executable must be a real file: {executable}")
    return info, executable


def run_checked(
    runner: Runner, args: Sequence[str], *, label: str
) -> subprocess.CompletedProcess[str]:
    try:
        result = runner(
            list(args), check=False, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"{label} could not run: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "no diagnostic").strip()
        raise RuntimeError(f"{label} failed with exit {result.returncode}: {detail}")
    return result


def designated_requirement(app: Path, *, runner: Runner = subprocess.run) -> str:
    result = run_checked(
        runner, ["codesign", "-d", "-r-", str(app)], label=f"inspect signature for {app}"
    )
    # codesign normally writes both the Executable path and requirement to
    # stderr.  Paths necessarily differ between candidate, stage, and install;
    # compare only the actual designated-requirement expression.
    for line in f"{result.stdout}\n{result.stderr}".splitlines():
        match = re.fullmatch(r"\s*designated\s*=>\s*(.+?)\s*", line)
        if match:
            return match.group(1)
    raise RuntimeError(f"codesign returned no designated requirement for {app}")


def verify_signed_app(app: Path, *, runner: Runner = subprocess.run) -> str:
    run_checked(
        runner,
        ["codesign", "--verify", "--deep", "--strict", str(app)],
        label=f"strict signature verification for {app}",
    )
    requirement = designated_requirement(app, runner=runner)
    if "cdhash" in requirement.lower() or "certificate" not in requirement.lower():
        raise RuntimeError(
            "Stable local installation requires a certificate-backed designated requirement"
        )
    return requirement


def verify_identity_available(identity: str, *, runner: Runner = subprocess.run) -> None:
    if not re.fullmatch(r"[0-9A-Fa-f]{40}", identity):
        raise RuntimeError("--signing-identity must be an exact 40-digit certificate SHA-1")
    result = run_checked(
        runner,
        ["security", "find-identity", "-v", "-p", "codesigning"],
        label="enumerate code-signing identities",
    )
    if not re.search(rf"(?im)^\s*\d+\)\s+{re.escape(identity)}\s+\"", result.stdout):
        raise RuntimeError(f"Requested signing identity is not available: {identity}")


def write_canonical_names(app: Path) -> None:
    info_path = app / "Contents" / "Info.plist"
    info = read_bundle_info(app)
    # Refuse to repair identity/executable mistakes.  Only the user-facing
    # names differ in review candidates and are deliberately canonicalized.
    if info.get("CFBundleIdentifier") != EXPECTED_BUNDLE_ID:
        raise RuntimeError("Staged bundle id changed during copy")
    if info.get("CFBundleExecutable") != EXPECTED_EXECUTABLE:
        raise RuntimeError("Staged executable changed during copy")
    info["CFBundleName"] = CANONICAL_APP_NAME
    info["CFBundleDisplayName"] = CANONICAL_APP_NAME
    with info_path.open("wb") as stream:
        plistlib.dump(info, stream, sort_keys=True)


def publish_exclusive_macos(source: Path, destination: Path) -> None:
    """Atomically rename without replacing anything at destination."""
    if os.uname().sysname != "Darwin":
        raise RuntimeError("Exclusive app publication is macOS-only")
    libc = ctypes.CDLL(None, use_errno=True)
    renamex_np = getattr(libc, "renamex_np", None)
    if renamex_np is None:
        raise RuntimeError("renamex_np is unavailable; refusing a non-exclusive fallback")
    renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    renamex_np.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = renamex_np(os.fsencode(source), os.fsencode(destination), RENAME_EXCL)
    if result != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise FileExistsError(
                error, "destination appeared during exclusive publish", destination
            )
        raise OSError(error, os.strerror(error), destination)


def install(
    source: Path,
    signing_identity: str,
    *,
    destination: Path = DESTINATION,
    runner: Runner = subprocess.run,
    publisher: Publisher = publish_exclusive_macos,
    lsregister: Path = LSREGISTER,
) -> dict:
    source = source.expanduser()
    if not source.is_absolute():
        source = Path.cwd() / source
    if source.is_symlink():
        raise RuntimeError(f"Source app itself must not be a symlink: {source}")
    source = source.resolve(strict=True)
    if destination != DESTINATION and runner is subprocess.run:
        raise RuntimeError(f"The production installer only supports {DESTINATION}")
    if path_exists_at_all(destination):
        raise FileExistsError(f"Refusing to replace existing destination: {destination}")
    if destination.parent.is_symlink() or not destination.parent.is_dir():
        raise RuntimeError(f"Destination parent must be a real directory: {destination.parent}")

    _, source_binary = validate_bundle_layout(source)
    source_requirement = verify_signed_app(source, runner=runner)
    verify_identity_available(signing_identity, runner=runner)
    source_sha = sha256(source_binary)

    stage_root = Path(
        tempfile.mkdtemp(prefix=".cua-driver-local-install-", dir=destination.parent)
    )
    stage_app = stage_root / DESTINATION.name
    try:
        run_checked(runner, ["ditto", str(source), str(stage_app)], label="copy candidate bundle")
        validate_bundle_layout(stage_app)
        write_canonical_names(stage_app)
        run_checked(
            runner,
            [
                "codesign", "--force", "--sign", signing_identity,
                "--timestamp=none", str(stage_app),
            ],
            label="sign canonical local bundle",
        )
        stage_requirement = verify_signed_app(stage_app, runner=runner)
        if stage_requirement != source_requirement:
            raise RuntimeError(
                "Re-signing changed the designated requirement; refusing installation\n"
                f"source: {source_requirement}\nstaged: {stage_requirement}"
            )
        _, stage_binary = validate_bundle_layout(stage_app)
        installed_sha = sha256(stage_binary)

        # The preflight above is useful for diagnostics; RENAME_EXCL is the
        # actual race-safe guard if another path appears before publication.
        if path_exists_at_all(destination):
            raise FileExistsError(f"Destination appeared before publish: {destination}")
        publisher(stage_app, destination)

        installed_info, installed_binary = validate_bundle_layout(destination)
        installed_requirement = verify_signed_app(destination, runner=runner)
        if installed_requirement != source_requirement:
            raise RuntimeError("Published app designated requirement differs from reviewed source")
        if sha256(installed_binary) != installed_sha:
            raise RuntimeError("Published executable differs from the verified staged executable")
        if installed_info.get("CFBundleName") != CANONICAL_APP_NAME:
            raise RuntimeError("Published app does not have the canonical bundle name")
        if installed_info.get("CFBundleDisplayName") != CANONICAL_APP_NAME:
            raise RuntimeError("Published app does not have the canonical display name")

        if not lsregister.is_file():
            raise RuntimeError(f"LaunchServices registrar is unavailable: {lsregister}")
        run_checked(
            runner, [str(lsregister), "-f", str(destination)],
            label="register stable local bundle with LaunchServices",
        )
        return {
            "source_app": str(source),
            "destination": str(destination),
            "bundle_id": EXPECTED_BUNDLE_ID,
            "bundle_name": CANONICAL_APP_NAME,
            "signing_identity": signing_identity.upper(),
            "designated_requirement": installed_requirement,
            "source_binary_sha256": source_sha,
            "installed_binary_sha256": installed_sha,
            "binary_resigned": source_sha != installed_sha,
            "daemon_changed": False,
            "cli_changed": False,
            "tcc_changed": False,
            "stock_driver_changed": False,
        }
    finally:
        # After publication the app has moved out of stage_root.  Never remove
        # or roll back the fixed destination here, even if registration fails.
        shutil.rmtree(stage_root, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-app", type=Path, required=True)
    parser.add_argument("--signing-identity", required=True)
    args = parser.parse_args()
    if os.uname().sysname != "Darwin":
        parser.error("This installer is macOS-only")
    try:
        report = install(args.source_app, args.signing_identity)
    except Exception as exc:
        raise SystemExit(f"install_patched_driver: {exc}") from exc
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
