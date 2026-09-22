import importlib.util
from pathlib import Path
import subprocess

import pytest


spec = importlib.util.spec_from_file_location(
    "candidate_build_output",
    Path(__file__).resolve().parents[1] / "scripts/build_patched_driver.py",
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_default_output_remains_cua_driver_local(tmp_path):
    app, binary = builder.output_paths("CuaDriverLocal", output=tmp_path)

    assert app == tmp_path.resolve() / "CuaDriverLocal.app"
    assert binary == app / "Contents/MacOS/cua-driver-local"


def test_named_output_stays_under_generated_root(tmp_path):
    app, binary = builder.output_paths("CuaDriverCandidate7", output=tmp_path)

    assert app == tmp_path.resolve() / "CuaDriverCandidate7.app"
    assert binary.parent.parent.parent == app
    assert app.parent == tmp_path.resolve()


@pytest.mark.parametrize("name", [
    "", ".hidden", ".", "..", "../candidate", "nested/candidate", "/tmp/candidate",
    "CuaDriver.app", "space name", "candidate;rm",
])
def test_app_name_rejects_paths_suffixes_and_unsafe_names(name):
    with pytest.raises(ValueError):
        builder.valid_app_name(name)


def test_existing_unmapped_binary_allows_overwrite_check(tmp_path):
    binary = tmp_path / "Candidate.app/Contents/MacOS/cua-driver-local"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"candidate")
    calls = []

    def lsof(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 1, "", "")

    assert builder.refuse_live_output_binary(binary, runner=lsof) is None
    assert calls == [(
        ["lsof", "-t", "--", str(binary)],
        {"check": False, "capture_output": True, "text": True, "timeout": 10},
    )]


def test_existing_mapped_binary_refuses_before_overwrite(tmp_path):
    binary = tmp_path / "Candidate.app/Contents/MacOS/cua-driver-local"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"candidate")

    def lsof(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "123\n456\n", "")

    with pytest.raises(RuntimeError, match="currently mapped by PID\\(s\\) 123, 456") as exc:
        builder.refuse_live_output_binary(binary, runner=lsof)
    assert "--app-name NAME" in str(exc.value)


@pytest.mark.parametrize("result", [
    subprocess.CompletedProcess(["lsof"], 0, "", ""),
    subprocess.CompletedProcess(["lsof"], 2, "", "permission denied"),
    subprocess.CompletedProcess(["lsof"], 1, "not-a-pid\n", ""),
])
def test_inconclusive_lsof_refuses_overwrite(tmp_path, result):
    binary = tmp_path / "Candidate.app/Contents/MacOS/cua-driver-local"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"candidate")

    with pytest.raises(RuntimeError, match="Cannot determine whether"):
        builder.refuse_live_output_binary(binary, runner=lambda *args, **kwargs: result)


def test_lsof_failure_refuses_overwrite(tmp_path):
    binary = tmp_path / "Candidate.app/Contents/MacOS/cua-driver-local"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"candidate")

    with pytest.raises(RuntimeError, match="Cannot determine whether"):
        builder.refuse_live_output_binary(
            binary,
            runner=lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("lsof")),
        )
