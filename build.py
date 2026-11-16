#!/usr/bin/env python3
"""Build a standalone program with PyInstaller.

    py -m pip install pyinstaller        (Windows)
    py build.py                          -> dist/VanquishModManager.exe

    python3 -m pip install pyinstaller   (Linux / macOS)
    python3 build.py                     -> dist/VanquishModManager
    python3 build.py --portable-zip      -> also dist/VanquishModManager-<ver>-linux-portable.zip
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "VanquishModManager"


def version() -> str:
    ns: dict = {}
    exec((ROOT / "vanquish" / "__init__.py").read_text(encoding="utf-8"), ns)
    return ns["__version__"]


def build() -> Path:
    assets = ROOT / "vanquish" / "assets"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
           "--name", NAME,
           "--add-data", f"{assets}{os.pathsep}vanquish/assets",
           "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"),
           "--specpath", str(ROOT / "build")]
    if platform.system() == "Windows":
        cmd += ["--icon", str(assets / "icon.ico")]
    elif platform.system() == "Darwin":
        cmd += ["--icon", str(assets / "icon.png")]
    cmd.append(str(ROOT / "main.py"))
    subprocess.run(cmd, check=True)
    exe = ROOT / "dist" / (NAME + (".exe" if platform.system() == "Windows" else ""))
    print(f"Built {exe}")
    return exe


def portable_zip(exe: Path) -> Path:
    """Zip the program with portable.txt, so all data stays next to it."""
    system = {"Windows": "windows", "Darwin": "macos"}.get(platform.system(), "linux")
    out = ROOT / "dist" / f"{NAME}-{version()}-{system}-portable.zip"
    folder = NAME
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo(f"{folder}/{exe.name}", time.localtime()[:6])
        info.external_attr = 0o755 << 16  # keep it executable
        info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(info, exe.read_bytes())
        zf.writestr(f"{folder}/portable.txt",
                    "This file makes the launcher keep all its data in the 'data' folder next to it.\n")
        zf.write(ROOT / "vanquish" / "assets" / "icon.png", f"{folder}/icon.png")
        zf.write(ROOT / "README.md", f"{folder}/README.md")
    print(f"Built {out}")
    return out


if __name__ == "__main__":
    if shutil.which("pyinstaller") is None:
        try:
            import PyInstaller  # noqa: F401
        except ImportError:
            sys.exit("PyInstaller is not installed: python -m pip install pyinstaller")
    exe = build()
    if "--portable-zip" in sys.argv:
        portable_zip(exe)
