"""Finding, checking and downloading Java runtimes."""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import tarfile
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import net
from .config import Paths
from .platform_utils import IS_LINUX, IS_MAC, IS_WINDOWS, is_within, machine_arch

JAVA_EXE = "javaw.exe" if IS_WINDOWS else "java"
ADOPTIUM_API = "https://api.adoptium.net/v3"


@dataclass
class JavaInstall:
    path: str
    version: str
    major: int
    arch: str

    @property
    def label(self) -> str:
        return f"Java {self.version} ({self.arch}) - {self.path}"


_probe_cache: dict[str, Optional[JavaInstall]] = {}


def _no_window_flags() -> int:
    return 0x08000000 if IS_WINDOWS else 0  # CREATE_NO_WINDOW


def parse_major(version: str) -> int:
    # "1.8.0_392" -> 8, "17.0.9" -> 17, "21" -> 21
    m = re.match(r"(\d+)(?:\.(\d+))?", version)
    if not m:
        return 0
    first = int(m.group(1))
    if first == 1 and m.group(2):
        return int(m.group(2))
    return first


def probe(java_path: str) -> Optional[JavaInstall]:
    """Run java once to learn its version and architecture."""
    key = os.path.realpath(java_path)
    if key in _probe_cache:
        return _probe_cache[key]
    result = None
    exe = java_path
    if IS_WINDOWS and exe.lower().endswith("javaw.exe"):
        cand = exe[:-9] + "java.exe"
        if os.path.exists(cand):
            exe = cand  # javaw prints nothing
    try:
        out = subprocess.run([exe, "-XshowSettings:properties", "-version"], capture_output=True,
                             text=True, timeout=15, creationflags=_no_window_flags())
        text = (out.stderr or "") + (out.stdout or "")
        ver = re.search(r"java\.version = (\S+)", text)
        arch = re.search(r"os\.arch = (\S+)", text)
        if ver:
            result = JavaInstall(java_path, ver.group(1), parse_major(ver.group(1)),
                                 arch.group(1) if arch else "?")
    except (OSError, subprocess.SubprocessError):
        result = None
    _probe_cache[key] = result
    return result


def _candidates(paths: Paths | None) -> list[str]:
    found: list[str] = []

    def add(p):
        if p and os.path.isfile(p) and p not in found:
            found.append(p)

    if paths is not None:
        for p in glob.glob(str(paths.java / "*" / "**" / "bin" / JAVA_EXE), recursive=True):
            add(p)
    jh = os.environ.get("JAVA_HOME")
    if jh:
        add(os.path.join(jh, "bin", JAVA_EXE))
    which = shutil.which("java")
    if which:
        add(os.path.realpath(which) if not IS_WINDOWS else which)
        if IS_WINDOWS:
            add(os.path.join(os.path.dirname(which), "javaw.exe"))
    patterns: list[str] = []
    if IS_WINDOWS:
        for base in filter(None, [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                                  os.environ.get("LOCALAPPDATA") and
                                  os.path.join(os.environ["LOCALAPPDATA"], "Programs")]):
            for vendor in ("Java", "Eclipse Adoptium", "Eclipse Foundation", "Microsoft", "Zulu",
                           "BellSoft", "Amazon Corretto", "Semeru", "AdoptOpenJDK"):
                patterns.append(os.path.join(base, vendor, "*", "bin", "javaw.exe"))
        mc_rt = os.path.join(os.environ.get("APPDATA", ""), ".minecraft", "runtime")
        patterns.append(os.path.join(mc_rt, "*", "*", "*", "bin", "javaw.exe"))
    elif IS_MAC:
        patterns += ["/Library/Java/JavaVirtualMachines/*/Contents/Home/bin/java",
                     os.path.expanduser("~/Library/Java/JavaVirtualMachines/*/Contents/Home/bin/java"),
                     "/opt/homebrew/opt/openjdk*/bin/java", "/usr/local/opt/openjdk*/bin/java",
                     os.path.expanduser("~/.sdkman/candidates/java/*/bin/java")]
    else:
        patterns += ["/usr/lib/jvm/*/bin/java", "/usr/lib64/jvm/*/bin/java", "/usr/java/*/bin/java",
                     "/opt/java/*/bin/java", "/opt/jdk*/bin/java",
                     os.path.expanduser("~/.sdkman/candidates/java/*/bin/java"),
                     os.path.expanduser("~/.jdks/*/bin/java")]
    for pat in patterns:
        for p in sorted(glob.glob(pat)):
            add(p)
    return found


def detect_all(paths: Paths | None = None) -> list[JavaInstall]:
    seen = set()
    installs = []
    for c in _candidates(paths):
        info = probe(c)
        if info is None:
            continue
        key = os.path.realpath(c)
        if key in seen:
            continue
        seen.add(key)
        installs.append(info)
    installs.sort(key=lambda j: (-j.major, j.path))
    return installs


def _arch_ok(java_arch: str) -> bool:
    a = java_arch.lower()
    mine = machine_arch()
    if mine == "arm64":
        return a in ("aarch64", "arm64") or IS_MAC  # Rosetta can run x64 Java
    if mine == "x86_64":
        return a in ("amd64", "x86_64")
    return True


def pick_java(required_major: int, paths: Paths | None = None) -> Optional[JavaInstall]:
    """Best installed Java for a version: exact major first, then newer ones (Java 8 must be 8)."""
    installs = [j for j in detect_all(paths) if _arch_ok(j.arch)] or detect_all(paths)
    exact = [j for j in installs if j.major == required_major]
    if exact:
        return exact[0]
    if required_major <= 8:
        return None  # old Forge/LaunchWrapper versions break on newer Java
    newer = sorted([j for j in installs if j.major > required_major], key=lambda j: j.major)
    return newer[0] if newer else None


# --------------------------------------------------------------------------- download

def _adoptium_os() -> str:
    return "windows" if IS_WINDOWS else "mac" if IS_MAC else "linux"


def _adoptium_arch() -> str:
    return {"x86_64": "x64", "arm64": "aarch64", "x86": "x32", "arm32": "arm"}.get(machine_arch(), "x64")


def _safe_extract(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            for m in zf.infolist():
                target = dest / m.filename
                if not is_within(target, dest):
                    raise ValueError(f"Unsafe path in archive: {m.filename}")
            zf.extractall(dest)
    else:
        with tarfile.open(archive, "r:gz") as tf:
            for m in tf.getmembers():
                if not is_within(dest / m.name, dest):
                    raise ValueError(f"Unsafe path in archive: {m.name}")
            try:
                tf.extractall(dest, filter="data")  # Python 3.12+
            except TypeError:
                tf.extractall(dest)


def download_java(paths: Paths, major: int, progress=None,
                  cancel: threading.Event | None = None) -> JavaInstall:
    """Download an Eclipse Temurin runtime into the launcher's java folder."""
    os_name, arch = _adoptium_os(), _adoptium_arch()
    attempts = [(arch, "jre"), (arch, "jdk")]
    if IS_MAC and arch == "aarch64":
        attempts += [("x64", "jre")]  # Java 8 has no Apple Silicon build; Rosetta runs x64
    last: Exception | None = None
    for a, image in attempts:
        try:
            if progress:
                progress(f"Looking up Java {major} ({image}, {a})...", None)
            assets = net.get_json(f"{ADOPTIUM_API}/assets/latest/{major}/hotspot",
                                  {"os": os_name, "architecture": a, "image_type": image,
                                   "vendor": "eclipse"})
            if not assets:
                raise ValueError("no build available")
            pkg = assets[0]["binary"]["package"]
            name = pkg["name"]
            archive = paths.cache / name
            if progress:
                progress(f"Downloading {name}...", None)
            net.download(pkg["link"], archive, cancel=cancel)
            target = paths.java / f"temurin-{major}-{image}-{a}"
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            if progress:
                progress("Extracting Java...", None)
            _safe_extract(archive, target)
            archive.unlink(missing_ok=True)
            exe = next(iter(glob.glob(str(target / "**" / "bin" / JAVA_EXE), recursive=True)), None)
            if not exe:
                raise ValueError("java executable not found in archive")
            if not IS_WINDOWS:
                os.chmod(exe, 0o755)
            _probe_cache.pop(os.path.realpath(exe), None)
            info = probe(exe)
            if not info:
                raise ValueError("downloaded Java does not run")
            return info
        except net.Cancelled:
            raise
        except Exception as e:
            last = e
    raise RuntimeError(f"Could not download Java {major}: {last}")


def linux_hint() -> str:
    if IS_LINUX:
        return "You can also install it with your package manager, e.g. 'sudo apt install openjdk-21-jre'."
    return ""
