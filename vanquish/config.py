"""Launcher-wide settings and on-disk layout."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .platform_utils import default_data_dir


def write_json_atomic(path: Path, data, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    if private:
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


@dataclass
class Settings:
    java_path: str = ""              # empty = pick automatically per Minecraft version
    min_memory: int = 512            # MiB
    max_memory: int = 4096           # MiB
    jvm_args: str = ""
    window_width: int = 854
    window_height: int = 480
    theme: str = "dark"              # dark | light
    close_on_launch: bool = False
    show_snapshots: bool = False
    msa_client_id: str = ""          # Azure application id for Microsoft login
    download_workers: int = 8
    window_geometry: str = ""
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        known = {f.name for f in fields(cls)}
        s = cls(**{k: v for k, v in (data or {}).items() if k in known})
        return s


class Paths:
    """All folders used by the launcher, rooted at one data directory."""

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else default_data_dir()
        self.instances = self.root / "instances"
        self.libraries = self.root / "libraries"
        self.assets = self.root / "assets"
        self.versions = self.root / "versions"
        self.java = self.root / "java"
        self.cache = self.root / "cache"
        self.logs = self.root / "logs"
        self.settings_file = self.root / "settings.json"
        self.accounts_file = self.root / "accounts.json"

    def ensure(self) -> "Paths":
        for p in (self.root, self.instances, self.libraries, self.assets, self.versions,
                  self.java, self.cache, self.logs):
            p.mkdir(parents=True, exist_ok=True)
        return self


class Config:
    def __init__(self, paths: Paths):
        self.paths = paths
        self.settings = Settings.from_dict(read_json(paths.settings_file, {}) or {})

    def save(self) -> None:
        write_json_atomic(self.paths.settings_file, asdict(self.settings))
