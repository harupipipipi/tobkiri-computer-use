"""Losslessly compress only this task's generated macOS Cargo cache.

Run after the native build has stopped. No user cache or installed app is touched.
Every replacement is checked byte-for-byte by SHA-256; the kernel transparently
decompresses these files. This reduces allocated blocks, not their logical size.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    cache = (ROOT / "artifacts/patched-driver/target").resolve(strict=True)
    if not cache.is_relative_to(ROOT):
        raise RuntimeError("Refusing a cache outside this checkout")
    files = sorted((p for p in cache.rglob("*") if p.is_file() and not p.is_symlink()
                    and p.stat().st_size > 256*1024), key=lambda p: p.stat().st_size, reverse=True)
    report = {"scope": "generated Cargo cache only", "files": []}
    for path in files:
        if not path.resolve().is_relative_to(cache):
            continue
        before = path.stat()
        if (before.st_blocks*512 < before.st_size*.8
                or shutil.disk_usage(cache).free < before.st_size + 256*2**20):
            continue
        temporary = path.with_name(path.name + ".tobkiri-compress")
        if temporary.exists():
            raise RuntimeError(f"Unexpected staging file: {temporary}")
        try:
            subprocess.run(["/usr/bin/ditto", "--hfsCompression", str(path), str(temporary)],
                           check=True, capture_output=True)
            after = temporary.stat()
            checksum = digest(path)
            if checksum != digest(temporary):
                raise RuntimeError(f"Content mismatch: {path}")
            if after.st_blocks < before.st_blocks:
                os.replace(temporary, path)
                report["files"].append({"path": str(path.relative_to(cache)), "sha256": checksum,
                                        "saved_bytes": (before.st_blocks-after.st_blocks)*512})
        finally:
            temporary.unlink(missing_ok=True)
    report["saved_mib"] = round(sum(row["saved_bytes"] for row in report["files"])/2**20, 2)
    (cache.parent / f"cache-compression-{time.time_ns()}.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({"files": len(report["files"]), "saved_mib": report["saved_mib"],
                      "free_mib": shutil.disk_usage(cache).free//2**20}))


if __name__ == "__main__":
    main()
