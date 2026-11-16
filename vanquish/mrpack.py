"""Importing Modrinth modpacks (.mrpack files)."""
from __future__ import annotations

import json
import shutil
import urllib.parse
import zipfile
from pathlib import Path

from . import net
from .instances import Instance, InstanceManager
from .platform_utils import is_within

SUPPORTED_LOADERS = {"fabric-loader": "fabric", "quilt-loader": "quilt"}
UNSUPPORTED_LOADERS = {"forge": "Forge", "neoforge": "NeoForge"}
ALLOWED_HOSTS = ("cdn.modrinth.com", "github.com", "raw.githubusercontent.com", "gitlab.com")


class PackError(Exception):
    pass


def _allowed(url: str) -> bool:
    """The .mrpack format only allows downloads from a few well-known hosts."""
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "https" and (parsed.hostname or "") in ALLOWED_HOSTS


def read_index(pack: Path) -> dict:
    try:
        with zipfile.ZipFile(pack) as zf:
            return json.loads(zf.read("modrinth.index.json").decode("utf-8"))
    except KeyError:
        raise PackError("This is not a Modrinth modpack (modrinth.index.json missing).")
    except (zipfile.BadZipFile, ValueError) as e:
        raise PackError(f"Could not read modpack: {e}")


def pack_info(index: dict) -> tuple[str, str, str]:
    """Returns (minecraft version, loader, loader version)."""
    deps = index.get("dependencies") or {}
    mc = deps.get("minecraft")
    if not mc:
        raise PackError("The modpack does not say which Minecraft version it needs.")
    for key, name in UNSUPPORTED_LOADERS.items():
        if key in deps:
            raise PackError(f"{name} modpacks are not supported yet (Fabric, Quilt and vanilla are).")
    for key, loader in SUPPORTED_LOADERS.items():
        if key in deps:
            return mc, loader, deps[key]
    return mc, "vanilla", ""


def install_pack(pack: Path, manager: InstanceManager, name: str = "", progress=None,
                 cancel=None, workers: int = 8) -> Instance:
    index = read_index(pack)
    mc, loader, loader_version = pack_info(index)
    inst = manager.create(name or index.get("name") or pack.stem, mc, loader, loader_version)
    try:
        game = inst.game_dir
        jobs = []
        for f in index.get("files", []):
            env = f.get("env") or {}
            if env.get("client") == "unsupported":
                continue
            dest = game / f["path"]
            if not is_within(dest, game):
                raise PackError(f"Unsafe file path in modpack: {f['path']}")
            urls = [u for u in (f.get("downloads") or []) if _allowed(u)]
            if not urls:
                raise PackError(f"No download from a trusted host for {f['path']}")
            jobs.append(net.DownloadJob(urls[0], dest, (f.get("hashes") or {}).get("sha1"),
                                        f.get("fileSize")))
        net.download_many(jobs, progress, "Downloading modpack files", workers=workers, cancel=cancel)
        if progress:
            progress("Copying overrides...", None)
        with zipfile.ZipFile(pack) as zf:
            for prefix in ("overrides/", "client-overrides/"):
                for m in zf.infolist():
                    if not m.filename.startswith(prefix) or m.is_dir():
                        continue
                    rel = m.filename[len(prefix):]
                    dest = game / rel
                    if not rel or not is_within(dest, game):
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(m) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
        inst.notes = index.get("summary", "") or ""
        inst.save()
        return inst
    except BaseException:
        manager.delete(inst)
        raise
