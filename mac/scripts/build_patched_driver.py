"""Build a separate signed Cua source bundle; never install or launch it.

No global driver, permission, daemon, or runtime setting is modified. Build
children are stopped if the disk reserve would be consumed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import signal
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/cua-source"
OUTPUT = ROOT / "artifacts/patched-driver"
PINNED_COMMIT = "fc188250b4ca8549b8e61f937fdb1fb560770e86"
APP_EXECUTABLE = "cua-driver-local"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signing_identity(explicit, previous=None):
    """Preserve a selected certificate on resume instead of reverting to ad-hoc."""
    selected = explicit if explicit is not None else (previous or {}).get("signing_identity", "-")
    if not isinstance(selected, str) or not selected.strip():
        raise ValueError("A signing identity must be a nonempty certificate identifier or '-'")
    return selected


def valid_app_name(value):
    """Return a safe bundle basename, never a path or a pre-suffixed app name."""
    if (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value)
            or value.endswith(".app")):
        raise ValueError(
            "--app-name must be one ASCII basename without .app "
            "(letters, digits, dot, underscore, and hyphen only)"
        )
    return value


def output_paths(app_name, *, output=OUTPUT):
    """Choose an app path that remains directly under the generated output root."""
    name = valid_app_name(app_name)
    root = output.resolve()
    app = (root / f"{name}.app").resolve()
    if app.parent != root:
        raise ValueError("The selected app output must remain directly under artifacts/patched-driver")
    return app, app / "Contents" / "MacOS" / APP_EXECUTABLE


def refuse_live_output_binary(binary, *, runner=subprocess.run):
    """Refuse to mutate a bundle binary that lsof cannot prove is unused."""
    try:
        binary.stat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RuntimeError(
            f"Cannot inspect existing output binary {binary}: {exc}; refusing to overwrite it. "
            "Use --app-name NAME to build a separate candidate."
        ) from exc
    try:
        result = runner(["lsof", "-t", "--", str(binary)], check=False, capture_output=True,
                        text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            f"Cannot determine whether existing output binary {binary} is in use: {exc}; "
            "refusing to overwrite it. Use --app-name NAME to build a separate candidate."
        ) from exc
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if result.returncode == 1 and not lines and not stderr.strip():
        return
    if result.returncode == 0 and lines and all(line.isdecimal() for line in lines):
        raise RuntimeError(
            f"Existing output binary {binary} is currently mapped by PID(s) {', '.join(lines)}; "
            "refusing to overwrite or sign it. Use --app-name NAME to build a separate candidate."
        )
    raise RuntimeError(
        f"Cannot determine whether existing output binary {binary} is in use "
        f"(lsof exit {result.returncode}, stdout={stdout!r}, stderr={stderr!r}); "
        "refusing to overwrite it. Use --app-name NAME to build a separate candidate."
    )


def run_build(command, cwd, env, log, reserve, timeout):
    start = time.monotonic()
    with log.open("w") as stream:
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=stream,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while proc.poll() is None:
                free = shutil.disk_usage(OUTPUT).free
                if free < reserve:
                    raise RuntimeError(f"Build stopped to preserve disk space: {free // 2**20} MiB free")
                if time.monotonic()-start > timeout:
                    raise RuntimeError("Build exceeded its time budget")
                time.sleep(1)
            if proc.returncode:
                raise RuntimeError(f"Build exited {proc.returncode}; see {log}")
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch", type=Path, action="append", required=True)
    parser.add_argument("--toolchain", default="stable", help="Use an already installed Rust toolchain")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Resume this generated build, appending patches to the recorded series")
    parser.add_argument("--compact-native", action="store_true", help="Optimize the large native workspace crates to reduce object-file size")
    parser.add_argument("--app-name", default="CuaDriverLocal",
                        help="Output bundle basename without .app (default: CuaDriverLocal)")
    parser.add_argument("--signing-identity", help="Existing codesigning certificate name/SHA-1; resume preserves the previous selection. New builds default to ad-hoc (-).")
    parser.add_argument("--reserve-mib", type=int, default=600)
    parser.add_argument("--timeout-minutes", type=int, default=25)
    args = parser.parse_args()
    if args.reserve_mib < 256 or args.timeout_minutes < 1:
        parser.error("Keep at least 256 MiB reserved and a positive time budget")
    try:
        app, binary = output_paths(args.app_name)
    except ValueError as exc:
        parser.error(str(exc))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    reserve = args.reserve_mib * 2**20
    if shutil.disk_usage(OUTPUT).free < reserve + (100 if args.resume else 400)*2**20:
        raise RuntimeError("Insufficient space for a bounded native build; nothing was changed")
    patches = [p.resolve(strict=True) for p in args.patch]
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=SOURCE,
                              check=True, capture_output=True, text=True).stdout.strip()
    if revision != PINNED_COMMIT:
        raise RuntimeError(f"Unexpected upstream revision: {revision}")
    # This is a generated source copy, distinct from upstream and worker files.
    source = OUTPUT / "source"
    applied = 0
    previous = None
    if source.exists():
        if not args.resume:
            raise RuntimeError(f"Generated source already exists; use --resume after reviewing its prior build report: {source}")
        previous = json.loads((OUTPUT / "build-report.json").read_text())
        recorded = previous.get("patches", [])
        if (previous.get("upstream_commit") != revision or not recorded
                or [p["sha256"] for p in recorded] != [sha(p) for p in patches[:len(recorded)]]):
            raise RuntimeError("Resume must keep the recorded patch series unchanged and may only append patches")
        applied = len(recorded)
        stamp = str(time.time_ns())
        for filename in ("build-report.json", "build.log"):
            if (OUTPUT / filename).exists():
                shutil.copy2(OUTPUT / filename, OUTPUT / f"previous-{stamp}-{filename}")
    else:
        if args.resume:
            raise RuntimeError("No generated build exists to resume")
        shutil.copytree(SOURCE, source, ignore=shutil.ignore_patterns(".git", "target", "__pycache__"))
    selected_identity = signing_identity(args.signing_identity, previous)
    for patch in patches[applied:]:
        subprocess.run(["git", "apply", "--check", str(patch)], cwd=source, check=True)
        subprocess.run(["git", "apply", str(patch)], cwd=source, check=True)
    env = dict(os.environ)
    env.update(CARGO_TARGET_DIR=str(OUTPUT / "target"), CARGO_BUILD_JOBS="2",
               CARGO_INCREMENTAL="0", CARGO_PROFILE_DEV_DEBUG="0", CARGO_PROFILE_TEST_DEBUG="0",
               CARGO_PROFILE_DEV_STRIP="debuginfo")
    workspace = source / "libs/cua-driver/rust"
    command = ["cargo", "+"+args.toolchain, "check" if args.check_only else "build",
               "--locked", "-p", "cua-driver", "--bin", "cua-driver"]
    if args.compact_native:
        for package in ("platform-macos", "cua-driver-core", "cua-driver-sdk", "cua-driver"):
            command.extend(["--config", f"profile.dev.package.{package}.opt-level=1",
                            "--config", f"profile.dev.package.{package}.codegen-units=4"])
    report = {"upstream": "cua-driver 0.28.2", "upstream_commit": revision,
              "patches": [{"path": str(p), "sha256": sha(p)} for p in patches],
              "command": command, "reserve_mib": args.reserve_mib, "installed": False,
              "launched": False, "existing_driver_changed": False, "permissions_changed": False,
              "signing_identity": selected_identity, "app_name": args.app_name,
              "app_output": str(app), "binary_output": str(binary),
              "output_binary_guard": "not_checked"}
    try:
        run_build(command, workspace, env, OUTPUT / "build.log", reserve, args.timeout_minutes*60)
        report["compiled"] = True
        if not args.check_only:
            refuse_live_output_binary(binary)
            report["output_binary_guard"] = "not_mapped_at_build_time"
            macos = app / "Contents/MacOS"
            macos.mkdir(parents=True, exist_ok=True)
            shutil.copy2(OUTPUT / "target/debug/cua-driver", binary)
            template = workspace / "scripts/CuaDriverBundle/Contents/Info.plist"
            shutil.copytree(template.parent / "Resources", app / "Contents/Resources", dirs_exist_ok=True)
            # Upstream's explanatory XML comment contains `--args`, which
            # strict XML parsers reject inside a comment. Strip comments only;
            # all actual plist keys and values still go through plistlib.
            info = plistlib.loads(re.sub(r"<!--.*?-->", "", template.read_text(), flags=re.S).encode())
            info.update(CFBundleIdentifier="com.trycua.driver.local", CFBundleName=args.app_name,
                        CFBundleDisplayName="Tobkiri Computer Use Driver", CFBundleExecutable=APP_EXECUTABLE,
                        CFBundleShortVersionString="0.28.2", CFBundleVersion="1")
            (app / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
            subprocess.run(["codesign", "--force", "--sign", selected_identity, "--timestamp=none", str(app)], check=True, timeout=60)
            subprocess.run(["codesign", "--verify", "--strict", str(app)], check=True, timeout=30)
            requirement = subprocess.run(["codesign", "-d", "-r-", str(app)], check=True,
                                         capture_output=True, text=True, timeout=30)
            report.update(app=str(app), binary_sha256=sha(binary),
                          signing=("ad-hoc; distinct from Cua release identity" if selected_identity == "-"
                                   else "existing local development certificate; distinct from Cua release identity"),
                          designated_requirement=(requirement.stdout + requirement.stderr).strip(),
                          os_permission_validation="pending trusted user setup")
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        (OUTPUT / "build-report.json").write_text(json.dumps(report, indent=2)+"\n")
        print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
