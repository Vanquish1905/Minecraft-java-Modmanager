"""Instances: self-contained game folders, each with its own version, loader and mods."""
from __future__ import annotations

import shutil
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional

from .config import Paths, read_json, write_json_atomic
from .platform_utils import safe_folder_name

INSTANCE_FILE = "instance.json"


@dataclass
class Instance:
    name: str
    mc_version: str
    loader: str = "vanilla"          # vanilla | fabric | quilt
    loader_version: str = ""
    version_id: str = ""             # id of the version json to launch (set after install)
    group: str = ""
    java_path: str = ""              # empty = use global setting / auto
    min_memory: int = 0              # 0 = use global setting
    max_memory: int = 0
    jvm_args: str = ""
    window_width: int = 0
    window_height: int = 0
    created: float = 0.0
    last_played: float = 0.0
    total_play_seconds: float = 0.0
    notes: str = ""
    folder: str = ""                 # not stored; filled when loaded

    @property
    def root(self) -> Path:
        return Path(self.folder)

    @property
    def game_dir(self) -> Path:
        return self.root / ".minecraft"

    @property
    def mods_dir(self) -> Path:
        return self.game_dir / "mods"

    @property
    def resourcepacks_dir(self) -> Path:
        return self.game_dir / "resourcepacks"

    @property
    def shaderpacks_dir(self) -> Path:
        return self.game_dir / "shaderpacks"

    @property
    def saves_dir(self) -> Path:
        return self.game_dir / "saves"

    @property
    def screenshots_dir(self) -> Path:
        return self.game_dir / "screenshots"

    @property
    def natives_dir(self) -> Path:
        return self.root / "natives"

    @property
    def id(self) -> str:
        return self.root.name

    @property
    def display_version(self) -> str:
        if self.loader == "vanilla":
            return self.mc_version
        label = {"fabric": "Fabric", "quilt": "Quilt"}.get(self.loader, self.loader)
        return f"{self.mc_version} · {label} {self.loader_version}".strip()

    def save(self) -> None:
        data = asdict(self)
        data.pop("folder", None)
        write_json_atomic(self.root / INSTANCE_FILE, data)

    @classmethod
    def load(cls, folder: Path) -> Optional["Instance"]:
        data = read_json(folder / INSTANCE_FILE)
        if not isinstance(data, dict) or "mc_version" not in data:
            return None
        known = {f.name for f in fields(cls)}
        inst = cls(**{k: v for k, v in data.items() if k in known and k != "folder"})
        inst.folder = str(folder)
        return inst


class InstanceManager:
    def __init__(self, paths: Paths):
        self.paths = paths

    def list(self) -> list[Instance]:
        out = []
        if not self.paths.instances.is_dir():
            return out
        for d in self.paths.instances.iterdir():
            if d.is_dir():
                inst = Instance.load(d)
                if inst:
                    out.append(inst)
        out.sort(key=lambda i: (i.group.lower(), i.name.lower()))
        return out

    def _unique_folder(self, name: str) -> Path:
        base = safe_folder_name(name)
        folder = self.paths.instances / base
        n = 1
        while folder.exists():
            n += 1
            folder = self.paths.instances / f"{base} ({n})"
        return folder

    def create(self, name: str, mc_version: str, loader: str = "vanilla",
               loader_version: str = "", group: str = "") -> Instance:
        name = name.strip() or mc_version
        folder = self._unique_folder(name)
        inst = Instance(name=name, mc_version=mc_version, loader=loader,
                        loader_version=loader_version, group=group, created=time.time(),
                        folder=str(folder))
        for sub in (inst.mods_dir, inst.resourcepacks_dir, inst.shaderpacks_dir, inst.saves_dir):
            sub.mkdir(parents=True, exist_ok=True)
        inst.save()
        return inst

    def delete(self, inst: Instance) -> None:
        root = inst.root.resolve()
        if root.parent != self.paths.instances.resolve():
            raise ValueError("Refusing to delete a folder outside the instances directory")
        shutil.rmtree(root)

    def copy(self, inst: Instance, new_name: str, include_saves: bool = True) -> Instance:
        folder = self._unique_folder(new_name)
        ignore = shutil.ignore_patterns("natives", *(["saves"] if not include_saves else []))
        shutil.copytree(inst.root, folder, ignore=ignore)
        new = Instance.load(folder)
        assert new is not None
        new.name = new_name
        new.created = time.time()
        new.last_played = 0.0
        new.total_play_seconds = 0.0
        new.save()
        return new

    def import_minecraft_folder(self, source: Path, inst: Instance) -> None:
        """Copy mods, configs, packs, worlds and options from an existing .minecraft folder."""
        for sub in ("mods", "config", "resourcepacks", "shaderpacks", "saves", "schematics"):
            src = source / sub
            if src.is_dir():
                shutil.copytree(src, inst.game_dir / sub, dirs_exist_ok=True)
        for f in ("options.txt", "optionsof.txt", "servers.dat"):
            if (source / f).is_file():
                shutil.copy2(source / f, inst.game_dir / f)
