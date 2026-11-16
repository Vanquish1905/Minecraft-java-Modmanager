"""Mojang version manifests: fetching, merging, rule evaluation and installing files."""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import net
from .config import Paths, read_json, write_json_atomic
from .platform_utils import arch_bits, machine_arch, mojang_os_name, os_version

MANIFEST_URL = os.environ.get(
    "VANQUISH_MANIFEST_URL", "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json")
LIBRARIES_URL = "https://libraries.minecraft.net/"
RESOURCES_URL = os.environ.get("VANQUISH_RESOURCES_URL", "https://resources.download.minecraft.net/")


# --------------------------------------------------------------------------- manifest

def get_manifest(paths: Paths, refresh: bool = False) -> dict:
    cache = paths.cache / "version_manifest_v2.json"
    if not refresh:
        data = read_json(cache)
        if data:
            return data
    try:
        data = net.get_json(MANIFEST_URL)
        write_json_atomic(cache, data)
        return data
    except net.NetworkError:
        data = read_json(cache)
        if data:
            return data
        raise


def find_manifest_entry(manifest: dict, version_id: str) -> Optional[dict]:
    for v in manifest.get("versions", []):
        if v.get("id") == version_id:
            return v
    return None


# --------------------------------------------------------------------------- rules

def _arch_matches(rule_arch: str) -> bool:
    arch = machine_arch()
    rule_arch = rule_arch.lower()
    if rule_arch == "x86":
        return arch == "x86"
    if rule_arch in ("x86_64", "x64", "amd64"):
        return arch == "x86_64"
    if rule_arch in ("arm64", "aarch64"):
        return arch == "arm64"
    return rule_arch == arch


def rule_matches(rule: dict, features: dict | None = None) -> bool:
    features = features or {}
    osr = rule.get("os")
    if osr:
        name = osr.get("name")
        if name:
            # Some third-party manifests use e.g. "osx-arm64" / "linux-arm64".
            base, _, suffix = name.partition("-")
            if base != mojang_os_name():
                return False
            if suffix and not _arch_matches(suffix):
                return False
        if osr.get("arch") and not _arch_matches(osr["arch"]):
            return False
        if osr.get("version"):
            try:
                if not re.search(osr["version"], os_version()):
                    return False
            except re.error:
                pass
    for key, wanted in (rule.get("features") or {}).items():
        if bool(features.get(key, False)) != bool(wanted):
            return False
    return True


def rules_allow(rules: list | None, features: dict | None = None) -> bool:
    if not rules:
        return True
    allowed = False
    for rule in rules:
        if rule_matches(rule, features):
            allowed = rule.get("action", "allow") == "allow"
    return allowed


# --------------------------------------------------------------------------- maven

def maven_path(name: str) -> str:
    """'group:artifact:version[:classifier][@ext]' -> relative jar path."""
    ext = "jar"
    if "@" in name:
        name, ext = name.split("@", 1)
    parts = name.split(":")
    if len(parts) < 3:
        raise ValueError(f"Bad maven coordinate: {name}")
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else None
    filename = f"{artifact}-{version}" + (f"-{classifier}" if classifier else "") + f".{ext}"
    return "/".join(group.split(".") + [artifact, version, filename])


def library_key(name: str) -> str:
    """Identity of a library ignoring its version (used to de-duplicate)."""
    base = name.split("@", 1)[0]
    parts = base.split(":")
    if len(parts) >= 4:
        return f"{parts[0]}:{parts[1]}:{parts[3]}"
    return ":".join(parts[:2])


# --------------------------------------------------------------------------- version json

def version_json_path(paths: Paths, version_id: str) -> Path:
    return paths.versions / version_id / f"{version_id}.json"


def client_jar_path(paths: Paths, version_id: str) -> Path:
    return paths.versions / version_id / f"{version_id}.jar"


def fetch_version_json(paths: Paths, version_id: str, refresh: bool = False) -> dict:
    path = version_json_path(paths, version_id)
    if path.exists() and not refresh:
        data = read_json(path)
        if data:
            return data
    manifest = get_manifest(paths)
    entry = find_manifest_entry(manifest, version_id)
    if entry is None:
        manifest = get_manifest(paths, refresh=True)
        entry = find_manifest_entry(manifest, version_id)
    if entry is None:
        data = read_json(path)
        if data:
            return data
        raise ValueError(f"Unknown Minecraft version '{version_id}'")
    sha1 = entry.get("sha1")
    net.download(entry["url"], path, sha1=sha1)
    return read_json(path)


def merge_versions(child: dict, parent: dict) -> dict:
    """Apply a loader profile (child) on top of the vanilla version (parent)."""
    merged = dict(parent)
    for key, value in child.items():
        if key in ("libraries", "arguments", "inheritsFrom"):
            continue
        merged[key] = value
    # Child libraries win over parent ones with the same identity.
    # (Duplicates inside one file are kept: Mojang uses them with OS rules.)
    child_libs = list(child.get("libraries", []))
    child_keys = {library_key(lib["name"]) for lib in child_libs if lib.get("name")}
    libs = child_libs + [lib for lib in parent.get("libraries", [])
                         if not lib.get("name") or library_key(lib["name"]) not in child_keys]
    merged["libraries"] = libs
    if "arguments" in child or "arguments" in parent:
        pa = parent.get("arguments", {}) or {}
        ca = child.get("arguments", {}) or {}
        merged["arguments"] = {
            "game": list(pa.get("game", [])) + list(ca.get("game", [])),
            "jvm": list(pa.get("jvm", [])) + list(ca.get("jvm", [])),
        }
    merged["jar"] = child.get("jar") or parent.get("jar") or parent.get("id")
    merged["id"] = child.get("id", parent.get("id"))
    merged.pop("inheritsFrom", None)
    return merged


def resolve_version(paths: Paths, version_id: str) -> dict:
    """Load a version json and every parent it inherits from."""
    data = fetch_version_json(paths, version_id)
    depth = 0
    while data.get("inheritsFrom"):
        depth += 1
        if depth > 5:
            raise ValueError("Version inheritance is too deep")
        parent = fetch_version_json(paths, data["inheritsFrom"])
        data = merge_versions(data, parent)
    data.setdefault("jar", data.get("id"))
    return data


# --------------------------------------------------------------------------- libraries

@dataclass
class LibraryFile:
    path: Path
    url: Optional[str]
    sha1: Optional[str]
    size: Optional[int]
    native: bool          # legacy natives that must be extracted
    classpath: bool
    extract_exclude: tuple = ()


def _natives_classifier(lib: dict) -> Optional[str]:
    natives = lib.get("natives")
    if not natives:
        return None
    cls = natives.get(mojang_os_name())
    if not cls:
        return None
    return cls.replace("${arch}", arch_bits())


def library_files(paths: Paths, lib: dict) -> list[LibraryFile]:
    if not rules_allow(lib.get("rules")):
        return []
    name = lib.get("name", "")
    downloads = lib.get("downloads") or {}
    files: list[LibraryFile] = []

    artifact = downloads.get("artifact")
    has_legacy_natives = bool(lib.get("natives"))
    if artifact and artifact.get("path"):
        files.append(LibraryFile(paths.libraries / artifact["path"], artifact.get("url") or None,
                                 artifact.get("sha1"), artifact.get("size"), False, True))
    elif not downloads and name and not has_legacy_natives:
        # Maven style library (Fabric / Quilt): name + repository url.
        rel = maven_path(name)
        base = lib.get("url") or LIBRARIES_URL
        if not base.endswith("/"):
            base += "/"
        files.append(LibraryFile(paths.libraries / rel, base + rel, lib.get("sha1"),
                                 lib.get("size"), False, True))

    cls = _natives_classifier(lib)
    if cls:
        exclude = tuple((lib.get("extract") or {}).get("exclude", []))
        info = (downloads.get("classifiers") or {}).get(cls)
        if info and info.get("path"):
            files.append(LibraryFile(paths.libraries / info["path"], info.get("url") or None,
                                     info.get("sha1"), info.get("size"), True, False, exclude))
        elif name:
            rel = maven_path(f"{name}:{cls}")
            base = lib.get("url") or LIBRARIES_URL
            if not base.endswith("/"):
                base += "/"
            files.append(LibraryFile(paths.libraries / rel, base + rel, None, None, True, False, exclude))
    return files


def all_library_files(paths: Paths, version: dict) -> list[LibraryFile]:
    out: list[LibraryFile] = []
    for lib in version.get("libraries", []):
        out.extend(library_files(paths, lib))
    return out


def build_classpath(paths: Paths, version: dict) -> list[str]:
    seen = set()
    cp: list[str] = []
    for f in all_library_files(paths, version):
        if f.classpath and str(f.path) not in seen:
            seen.add(str(f.path))
            cp.append(str(f.path))
    cp.append(str(client_jar_path(paths, version["jar"])))
    return cp


def extract_natives(paths: Paths, version: dict, natives_dir: Path) -> None:
    if natives_dir.exists():
        shutil.rmtree(natives_dir, ignore_errors=True)
    natives_dir.mkdir(parents=True, exist_ok=True)
    for f in all_library_files(paths, version):
        if not f.native or not f.path.exists():
            continue
        with zipfile.ZipFile(f.path) as zf:
            for member in zf.infolist():
                n = member.filename
                if member.is_dir() or n.startswith("META-INF/"):
                    continue
                if any(n.startswith(ex) for ex in f.extract_exclude):
                    continue
                target = natives_dir / Path(n).name  # flatten, also defeats path traversal
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)


# --------------------------------------------------------------------------- assets

def asset_index_path(paths: Paths, version: dict) -> Path:
    idx = version.get("assetIndex") or {}
    return paths.assets / "indexes" / f"{idx.get('id', version.get('assets', 'legacy'))}.json"


def install_assets(paths: Paths, version: dict, progress=None, cancel=None, workers: int = 8) -> dict:
    idx = version.get("assetIndex")
    if not idx:
        return {}
    index_path = asset_index_path(paths, version)
    net.download(idx["url"], index_path, sha1=idx.get("sha1"), cancel=cancel)
    index = read_json(index_path, {}) or {}
    jobs = []
    for name, obj in (index.get("objects") or {}).items():
        h = obj["hash"]
        jobs.append(net.DownloadJob(f"{RESOURCES_URL}{h[:2]}/{h}", paths.assets / "objects" / h[:2] / h,
                                    h, obj.get("size")))
    net.download_many(jobs, progress, "Downloading assets", workers=workers, cancel=cancel)
    return index


def prepare_legacy_assets(paths: Paths, version: dict, game_dir: Path) -> Optional[Path]:
    """Old versions read assets by file name rather than hash; copy them out."""
    index = read_json(asset_index_path(paths, version), {}) or {}
    objects = index.get("objects") or {}
    target: Optional[Path] = None
    if index.get("map_to_resources"):
        target = game_dir / "resources"
    elif index.get("virtual"):
        target = paths.assets / "virtual" / (version.get("assetIndex") or {}).get("id", "legacy")
    if target is None:
        return None
    for name, obj in objects.items():
        dest = target / name
        if not str(dest.resolve()).startswith(str(target.resolve())):
            continue
        if dest.exists():
            continue
        src = paths.assets / "objects" / obj["hash"][:2] / obj["hash"]
        if src.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
    return target


# --------------------------------------------------------------------------- install

def logging_config(paths: Paths, version: dict) -> Optional[tuple[Path, str]]:
    client = ((version.get("logging") or {}).get("client")) or {}
    f = client.get("file")
    if not f or not client.get("argument"):
        return None
    return paths.assets / "log_configs" / f["id"], client["argument"]


def install_version(paths: Paths, version_id: str, progress=None,
                    cancel: threading.Event | None = None, workers: int = 8) -> dict:
    """Make sure every file needed to run `version_id` is present. Returns merged json."""
    def report(text, frac=None):
        if progress:
            progress(text, frac)

    report(f"Resolving {version_id}...", None)
    version = resolve_version(paths, version_id)

    jobs: list[net.DownloadJob] = []
    client = (version.get("downloads") or {}).get("client")
    jar = client_jar_path(paths, version["jar"])
    if client:
        jobs.append(net.DownloadJob(client["url"], jar, client.get("sha1"), client.get("size")))
    elif not jar.exists():
        raise ValueError(f"No client download for {version['jar']}")

    missing_url = []
    for f in all_library_files(paths, version):
        if f.url:
            jobs.append(net.DownloadJob(f.url, f.path, f.sha1, f.size))
        elif not f.path.exists():
            missing_url.append(f.path.name)
    if missing_url:
        raise ValueError("Libraries without download location are missing: " + ", ".join(missing_url))

    log_cfg = (version.get("logging") or {}).get("client", {}).get("file")
    if log_cfg:
        jobs.append(net.DownloadJob(log_cfg["url"], paths.assets / "log_configs" / log_cfg["id"],
                                    log_cfg.get("sha1"), log_cfg.get("size")))

    net.download_many(jobs, progress, "Downloading libraries", workers=workers, cancel=cancel)
    install_assets(paths, version, progress, cancel, workers=workers)
    report("Game files ready", 1.0)
    return version


def required_java(version: dict) -> int:
    jv = version.get("javaVersion") or {}
    major = jv.get("majorVersion")
    if major:
        return int(major)
    return 8


def version_list(manifest: dict, include_snapshots: bool = False, include_old: bool = False) -> list[dict]:
    out = []
    for v in manifest.get("versions", []):
        t = v.get("type")
        if t == "release" or (include_snapshots and t == "snapshot") or \
                (include_old and t in ("old_beta", "old_alpha")):
            out.append(v)
    return out


def dump(obj) -> str:  # small helper for debugging
    return json.dumps(obj, indent=2)
