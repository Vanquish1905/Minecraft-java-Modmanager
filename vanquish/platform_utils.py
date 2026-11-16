"""Operating-system specific helpers (paths, architecture, opening folders)."""
from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
from pathlib import Path

SYSTEM = platform.system()
IS_WINDOWS = SYSTEM == "Windows"
IS_MAC = SYSTEM == "Darwin"
IS_LINUX = not (IS_WINDOWS or IS_MAC)


def mojang_os_name() -> str:
    """OS name as used by Mojang's version manifests."""
    if IS_WINDOWS:
        return "windows"
    if IS_MAC:
        return "osx"
    return "linux"


def machine_arch() -> str:
    """Normalised CPU architecture: x86_64, x86, arm64 or arm32."""
    m = platform.machine().lower()
    if m in ("amd64", "x86_64", "x64"):
        return "x86_64"
    if m in ("i386", "i486", "i586", "i686", "x86"):
        return "x86"
    if m in ("arm64", "aarch64", "armv8", "armv8l"):
        return "arm64"
    if m.startswith("arm"):
        return "arm32"
    return m or "x86_64"


def arch_bits() -> str:
    return "32" if machine_arch() in ("x86", "arm32") else "64"


def os_version() -> str:
    if IS_MAC:
        return platform.mac_ver()[0] or platform.release()
    return platform.release()


def default_data_dir() -> Path:
    """Where the launcher stores instances, libraries, assets and settings."""
    override = os.environ.get("VANQUISH_DATA_DIR")
    if override:
        return Path(override).expanduser()
    # Portable mode: a file named "portable.txt" next to the program.
    here = Path(sys.argv[0]).resolve().parent if sys.argv and sys.argv[0] else Path.cwd()
    if (here / "portable.txt").exists():
        return here / "data"
    home = Path.home()
    if IS_WINDOWS:
        base = os.environ.get("APPDATA")
        return (Path(base) if base else home / "AppData" / "Roaming") / "VanquishModManager"
    if IS_MAC:
        return home / "Library" / "Application Support" / "VanquishModManager"
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else home / ".local" / "share") / "vanquish-modmanager"


def official_minecraft_dir() -> Path:
    """The vanilla launcher's .minecraft folder for this OS."""
    home = Path.home()
    if IS_WINDOWS:
        base = os.environ.get("APPDATA")
        return (Path(base) if base else home / "AppData" / "Roaming") / ".minecraft"
    if IS_MAC:
        return home / "Library" / "Application Support" / "minecraft"
    flatpak = home / ".var" / "app" / "com.mojang.Minecraft" / ".minecraft"
    if not (home / ".minecraft").exists() and flatpak.exists():
        return flatpak
    return home / ".minecraft"


def open_path(path: os.PathLike | str) -> None:
    """Open a file or folder in the system file manager / default app."""
    path = str(path)
    if IS_WINDOWS:
        os.startfile(path)  # type: ignore[attr-defined]
    elif IS_MAC:
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


_INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_WINDOWS = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                     *(f"LPT{i}" for i in range(1, 10))}


def safe_folder_name(name: str) -> str:
    """Turn a display name into a folder name valid on every OS."""
    cleaned = _INVALID_NAME_CHARS.sub("_", name).strip().strip(".")
    if not cleaned:
        cleaned = "instance"
    if cleaned.upper() in _RESERVED_WINDOWS:
        cleaned = "_" + cleaned
    return cleaned[:64]


def is_within(child: Path, parent: Path) -> bool:
    """True if `child` resolves to a location inside `parent`."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def human_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, _ = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
