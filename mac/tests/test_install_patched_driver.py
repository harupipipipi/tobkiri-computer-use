from __future__ import annotations

import importlib.util
import errno
from pathlib import Path
import plistlib
import shutil
import subprocess
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "install_patched_driver.py"
SPEC = importlib.util.spec_from_file_location("install_patched_driver", SCRIPT)
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)

IDENTITY = "18AB2B4F2EB309BC4ACD28A1DEE020C4B75657C2"
REQUIREMENT = (
    'identifier "com.trycua.driver.local" and anchor apple generic and '
    'certificate leaf[subject.CN] = "Apple Development: Fixture (TEAMID)"'
)


def make_app(path: Path, *, bundle_id=installer.EXPECTED_BUNDLE_ID) -> Path:
    executable = path / "Contents" / "MacOS" / installer.EXPECTED_EXECUTABLE
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"reviewed native executable")
    info = {
        "CFBundleIdentifier": bundle_id,
        "CFBundleExecutable": installer.EXPECTED_EXECUTABLE,
        "CFBundleName": "CuaDriverCandidate12",
        "CFBundleDisplayName": "Tobkiri Computer Use Driver",
    }
    with (path / "Contents" / "Info.plist").open("wb") as stream:
        plistlib.dump(info, stream)
    return path


class FakeRunner:
    def __init__(self, *, staged_requirement=REQUIREMENT):
        self.calls = []
        self.staged_requirement = staged_requirement

    def __call__(self, args, **_kwargs):
        args = [str(arg) for arg in args]
        self.calls.append(args)
        if args[0] == "ditto":
            shutil.copytree(args[1], args[2])
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:4] == ["security", "find-identity", "-v", "-p"]:
            stdout = f'  1) {IDENTITY} "Apple Development: Fixture (TEAMID)"\n'
            return subprocess.CompletedProcess(args, 0, stdout, "")
        if args[:3] == ["codesign", "-d", "-r-"]:
            app = Path(args[-1])
            requirement = (
                self.staged_requirement
                if app.name == installer.DESTINATION.name
                else REQUIREMENT
            )
            stderr = (
                f"Executable={app}/Contents/MacOS/cua-driver-local\n"
                f"designated => {requirement}\n"
            )
            return subprocess.CompletedProcess(args, 0, "", stderr)
        return subprocess.CompletedProcess(args, 0, "", "")


def test_designated_requirement_ignores_executable_path(tmp_path):
    app = make_app(tmp_path / "Candidate.app")
    runner = FakeRunner()
    assert installer.designated_requirement(app, runner=runner) == REQUIREMENT


@pytest.mark.parametrize("kind", ["directory", "symlink"])
def test_existing_destination_is_never_replaced(tmp_path, kind):
    source = make_app(tmp_path / "Candidate.app")
    destination = tmp_path / "CuaDriverLocal.app"
    if kind == "directory":
        destination.mkdir()
    else:
        destination.symlink_to(tmp_path / "missing")
    with pytest.raises(FileExistsError, match="Refusing to replace"):
        installer.install(
            source,
            IDENTITY,
            destination=destination,
            runner=FakeRunner(),
            publisher=lambda _source, _destination: pytest.fail("must not publish"),
            lsregister=tmp_path / "lsregister",
        )


def test_source_app_symlink_is_rejected(tmp_path):
    real_source = make_app(tmp_path / "Candidate.app")
    source_link = tmp_path / "CandidateLink.app"
    source_link.symlink_to(real_source)
    with pytest.raises(RuntimeError, match="must not be a symlink"):
        installer.install(
            source_link,
            IDENTITY,
            destination=tmp_path / "CuaDriverLocal.app",
            runner=FakeRunner(),
            publisher=lambda _source, _destination: pytest.fail("must not publish"),
            lsregister=tmp_path / "lsregister",
        )


def test_macos_publish_uses_rename_excl_and_surfaces_race(tmp_path, monkeypatch):
    calls = []

    class Rename:
        argtypes = None
        restype = None

        def __call__(self, source, destination, flags):
            calls.append((source, destination, flags))
            installer.ctypes.set_errno(errno.EEXIST)
            return -1

    monkeypatch.setattr(installer.os, "uname", lambda: SimpleNamespace(sysname="Darwin"))
    monkeypatch.setattr(
        installer.ctypes, "CDLL", lambda *_args, **_kwargs: SimpleNamespace(renamex_np=Rename())
    )
    destination = tmp_path / "CuaDriverLocal.app"
    with pytest.raises(FileExistsError, match="destination appeared"):
        installer.publish_exclusive_macos(tmp_path / "stage.app", destination)
    assert calls[0][2] == installer.RENAME_EXCL


def test_signature_requirement_change_is_rejected_before_publish(tmp_path):
    source = make_app(tmp_path / "Candidate.app")
    destination = tmp_path / "CuaDriverLocal.app"
    lsregister = tmp_path / "lsregister"
    lsregister.write_text("")
    runner = FakeRunner(
        staged_requirement=REQUIREMENT + " and certificate leaf[subject.OU] = OTHER"
    )
    with pytest.raises(RuntimeError, match="changed the designated requirement"):
        installer.install(
            source,
            IDENTITY,
            destination=destination,
            runner=runner,
            publisher=lambda _source, _destination: pytest.fail("must not publish"),
            lsregister=lsregister,
        )
    assert not installer.path_exists_at_all(destination)


def test_publish_race_does_not_replace_competing_path(tmp_path):
    source = make_app(tmp_path / "Candidate.app")
    destination = tmp_path / "CuaDriverLocal.app"
    lsregister = tmp_path / "lsregister"
    lsregister.write_text("")

    def racing_publisher(_source, target):
        target.symlink_to(tmp_path / "competitor")
        raise FileExistsError("destination appeared during exclusive publish")

    with pytest.raises(FileExistsError, match="destination appeared"):
        installer.install(
            source,
            IDENTITY,
            destination=destination,
            runner=FakeRunner(),
            publisher=racing_publisher,
            lsregister=lsregister,
        )
    assert destination.is_symlink()
    assert destination.readlink() == tmp_path / "competitor"


def test_initial_install_canonicalizes_and_only_registers(tmp_path):
    source = make_app(tmp_path / "Candidate.app")
    destination = tmp_path / "CuaDriverLocal.app"
    lsregister = tmp_path / "lsregister"
    lsregister.write_text("")
    runner = FakeRunner()

    def publish(stage, target):
        # os.rename is adequate in this isolated test; production calls the
        # macOS RENAME_EXCL implementation.
        stage.rename(target)

    report = installer.install(
        source,
        IDENTITY,
        destination=destination,
        runner=runner,
        publisher=publish,
        lsregister=lsregister,
    )

    info = installer.read_bundle_info(destination)
    assert info["CFBundleName"] == "Cua Driver Local"
    assert info["CFBundleDisplayName"] == "Cua Driver Local"
    assert info["CFBundleIdentifier"] == installer.EXPECTED_BUNDLE_ID
    assert info["CFBundleExecutable"] == installer.EXPECTED_EXECUTABLE
    assert report["designated_requirement"] == REQUIREMENT
    assert report["daemon_changed"] is False
    assert report["cli_changed"] is False
    assert report["tcc_changed"] is False
    assert report["stock_driver_changed"] is False
    assert [str(lsregister), "-f", str(destination)] in runner.calls
    flattened = "\n".join(" ".join(call) for call in runner.calls)
    assert "tccutil" not in flattened
    assert "pkill" not in flattened
    assert "launchctl" not in flattened
    assert "CuaDriver.app" not in flattened
