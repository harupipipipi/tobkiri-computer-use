"""Build the disposable WinForms acceptance fixture with the inbox C# compiler."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = root / "tests" / "fixtures" / "WindowsComputerFixture.cs"
    compiler = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
    if not compiler.exists():
        raise FileNotFoundError("The Windows .NET Framework C# compiler is unavailable")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        str(compiler), "/nologo", "/target:winexe", "/optimize+",
        "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll",
        "/out:" + str(args.output), str(source),
    ], check=True)
    print(str(args.output.resolve()))


if __name__ == "__main__":
    main()
