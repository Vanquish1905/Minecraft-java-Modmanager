"""Reading mod metadata and managing mod / resource pack / shader pack files."""
from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    tomllib = None

DISABLED_SUFFIX = ".disabled"


@dataclass
class ModFile:
    path: Path
    name: str
    version: str = ""
    mod_id: str = ""
    loaders: list = field(default_factory=list)   # e.g. ["fabric"]
    description: str = ""
    authors: str = ""
    mc_version: str = ""

    @property
    def enabled(self) -> bool:
        return not self.path.name.endswith(DISABLED_SUFFIX)

    @property
    def filename(self) -> str:
        n = self.path.name
        return n[:-len(DISABLED_SUFFIX)] if n.endswith(DISABLED_SUFFIX) else n


# --------------------------------------------------------------------------- parsing helpers

def _loads_json(raw: bytes):
    text = raw.decode("utf-8", errors="replace").lstrip("﻿")
    try:
        return json.loads(text)
    except ValueError:
        # Some mods ship json with literal newlines inside strings.
        return json.loads(text.replace("\n", " ").replace("\r", " "))


def _mini_toml(text: str) -> dict:
    """Very small TOML subset parser used when tomllib is unavailable."""
    root: dict = {}
    cur = root
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\[\[\s*([\w.]+)\s*\]\]$", line)
        if m:
            cur = {}
            root.setdefault(m.group(1), []).append(cur)
            continue
        m = re.match(r"^\[\s*([\w.]+)\s*\]$", line)
        if m:
            cur = root.setdefault(m.group(1), {})
            if isinstance(cur, list):
                cur = {}
            continue
        m = re.match(r'^([\w.-]+)\s*=\s*(.+)$', line)
        if m:
            val = m.group(2).strip()
            if val.startswith('"""') or val.startswith("'''"):
                val = val.strip("\"'")
            elif val[:1] in "\"'":
                q = val[0]
                end = val.find(q, 1)
                val = val[1:end] if end > 0 else val[1:]
            else:
                val = val.split("#", 1)[0].strip()
            cur[m.group(1)] = val
    return root


def _toml(raw: bytes) -> dict:
    text = raw.decode("utf-8", errors="replace")
    if tomllib is not None:
        try:
            return tomllib.loads(text)
        except Exception:
            pass
    return _mini_toml(text)


def _manifest_version(zf: zipfile.ZipFile) -> str:
    try:
        text = zf.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")
        m = re.search(r"^Implementation-Version:\s*(.+)$", text, re.M)
        return m.group(1).strip() if m else ""
    except KeyError:
        return ""


def _authors(value) -> str:
    if isinstance(value, str):
        return value
    out = []
    for a in value or []:
        out.append(a.get("name", "") if isinstance(a, dict) else str(a))
    return ", ".join(x for x in out if x)


def read_mod_metadata(path: Path) -> ModFile:
    mod = ModFile(path=path, name=path.name)
    base = mod.filename
    mod.name = base[:-4] if base.lower().endswith(".jar") else base
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            if "fabric.mod.json" in names:
                d = _loads_json(zf.read("fabric.mod.json"))
                mod.loaders.append("fabric")
                mod.mod_id = d.get("id", "")
                mod.name = d.get("name") or mod.mod_id or mod.name
                mod.version = str(d.get("version", ""))
                mod.description = d.get("description", "") or ""
                mod.authors = _authors(d.get("authors"))
                mc = (d.get("depends") or {}).get("minecraft")
                mod.mc_version = mc if isinstance(mc, str) else ", ".join(mc or [])
            if "quilt.mod.json" in names:
                d = _loads_json(zf.read("quilt.mod.json")).get("quilt_loader", {})
                meta = d.get("metadata", {})
                mod.loaders.append("quilt")
                mod.mod_id = mod.mod_id or d.get("id", "")
                mod.name = meta.get("name") or mod.name
                mod.version = mod.version or str(d.get("version", ""))
                mod.description = mod.description or meta.get("description", "")
                contrib = meta.get("contributors") or {}
                mod.authors = mod.authors or ", ".join(contrib.keys())
            for toml_name, loader in (("META-INF/neoforge.mods.toml", "neoforge"),
                                      ("META-INF/mods.toml", "forge")):
                if toml_name in names:
                    d = _toml(zf.read(toml_name))
                    entries = d.get("mods") or [{}]
                    first = entries[0] if isinstance(entries, list) and entries else {}
                    mod.loaders.append(loader)
                    mod.mod_id = mod.mod_id or first.get("modId", "")
                    mod.name = first.get("displayName") or mod.name
                    ver = str(first.get("version", ""))
                    if "${" in ver:
                        ver = _manifest_version(zf) or ""
                    mod.version = mod.version or ver
                    mod.description = mod.description or str(first.get("description", "")).strip()
                    mod.authors = mod.authors or str(first.get("authors", ""))
                    break
            if "mcmod.info" in names and not mod.loaders:
                d = _loads_json(zf.read("mcmod.info"))
                if isinstance(d, dict):
                    d = d.get("modList") or d.get("modlist") or []
                first = d[0] if d else {}
                mod.loaders.append("forge")
                mod.mod_id = first.get("modid", "")
                mod.name = first.get("name") or mod.name
                mod.version = str(first.get("version", ""))
                mod.description = first.get("description", "")
                mod.mc_version = first.get("mcversion", "")
                mod.authors = _authors(first.get("authorList") or first.get("authors"))
    except (zipfile.BadZipFile, OSError, ValueError, KeyError, AttributeError, TypeError, IndexError):
        pass
    return mod


_meta_cache: dict[tuple, ModFile] = {}


def _cached_metadata(path: Path) -> ModFile:
    st = path.stat()
    base = path.name[:-len(DISABLED_SUFFIX)] if path.name.endswith(DISABLED_SUFFIX) else path.name
    key = (str(path.parent), base, st.st_size, int(st.st_mtime))
    cached = _meta_cache.get(key)
    if cached is not None:
        cached.path = path
        return cached
    mod = read_mod_metadata(path)
    _meta_cache[key] = mod
    return mod


# --------------------------------------------------------------------------- folder management

CONTENT_EXTS = {
    "mods": (".jar", ".zip"),
    "resourcepacks": (".zip",),
    "shaderpacks": (".zip",),
}


def list_content(folder: Path, kind: str = "mods") -> list[ModFile]:
    if not folder.is_dir():
        return []
    exts = CONTENT_EXTS.get(kind, (".zip",))
    out = []
    for p in sorted(folder.iterdir(), key=lambda x: x.name.lower()):
        base = p.name[:-len(DISABLED_SUFFIX)] if p.name.endswith(DISABLED_SUFFIX) else p.name
        if p.is_file() and base.lower().endswith(exts):
            out.append(_cached_metadata(p) if kind == "mods" else ModFile(p, base))
        elif p.is_dir() and kind != "mods":
            out.append(ModFile(p, p.name))
    return out


def set_enabled(item: ModFile, enabled: bool) -> Path:
    p = item.path
    if enabled == item.enabled:
        return p
    if enabled:
        new = p.with_name(p.name[:-len(DISABLED_SUFFIX)])
    else:
        new = p.with_name(p.name + DISABLED_SUFFIX)
    if new.exists():
        raise FileExistsError(f"{new.name} already exists")
    p.rename(new)
    item.path = new
    return new


def remove(item: ModFile) -> None:
    if item.path.is_dir():
        shutil.rmtree(item.path)
    else:
        item.path.unlink()


def add_files(folder: Path, files: list[Path]) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    added = []
    for f in files:
        f = Path(f)
        dest = folder / f.name
        if f.resolve() == dest.resolve():
            continue
        if f.is_dir():
            shutil.copytree(f, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(f, dest)
        added.append(dest)
    return added


def loader_mismatch(mod: ModFile, instance_loader: str) -> bool:
    """True if a mod clearly targets a different loader than the instance."""
    if not mod.loaders or instance_loader == "vanilla":
        return instance_loader == "vanilla" and bool(mod.loaders)
    if instance_loader in mod.loaders:
        return False
    if instance_loader == "quilt" and "fabric" in mod.loaders:
        return False  # Quilt runs most Fabric mods
    return True


def find_duplicates(mods: list[ModFile]) -> dict[str, list[ModFile]]:
    by_id: dict[str, list[ModFile]] = {}
    for m in mods:
        if m.mod_id and m.enabled:
            by_id.setdefault(m.mod_id, []).append(m)
    return {k: v for k, v in by_id.items() if len(v) > 1}
