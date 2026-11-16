"""Mod loader support (Fabric and Quilt via their public meta APIs)."""
from __future__ import annotations

import os
import urllib.parse

from . import net
from .config import Paths, write_json_atomic
from .versions import version_json_path

LOADERS = {
    "fabric": {
        "label": "Fabric",
        "meta": os.environ.get("VANQUISH_FABRIC_META", "https://meta.fabricmc.net/v2"),
    },
    "quilt": {
        "label": "Quilt",
        "meta": os.environ.get("VANQUISH_QUILT_META", "https://meta.quiltmc.org/v3"),
    },
}

LOADER_CHOICES = ["vanilla", "fabric", "quilt"]
LOADER_LABELS = {"vanilla": "Vanilla", "fabric": "Fabric", "quilt": "Quilt"}


def _q(s: str) -> str:
    return urllib.parse.quote(s, safe="")


def loader_versions(loader: str, mc_version: str) -> list[dict]:
    """Newest first. Each item: {'version': str, 'stable': bool}."""
    meta = LOADERS[loader]["meta"]
    data = net.get_json(f"{meta}/versions/loader/{_q(mc_version)}")
    out = []
    for item in data or []:
        info = item.get("loader", item)
        ver = info.get("version")
        if not ver:
            continue
        stable = info.get("stable")
        if stable is None:  # Quilt marks pre-releases by name
            stable = "beta" not in ver and "pre" not in ver
        out.append({"version": ver, "stable": bool(stable)})
    return out


def recommended_loader_version(loader: str, mc_version: str) -> str:
    versions = loader_versions(loader, mc_version)
    if not versions:
        raise ValueError(f"{LOADERS[loader]['label']} does not support Minecraft {mc_version}")
    for v in versions:
        if v["stable"]:
            return v["version"]
    return versions[0]["version"]


def install_loader_profile(paths: Paths, loader: str, mc_version: str, loader_version: str) -> str:
    """Download the loader's launcher profile json. Returns the version id to launch."""
    if loader == "vanilla":
        return mc_version
    meta = LOADERS[loader]["meta"]
    profile = net.get_json(
        f"{meta}/versions/loader/{_q(mc_version)}/{_q(loader_version)}/profile/json")
    vid = profile.get("id") or f"{loader}-loader-{loader_version}-{mc_version}"
    profile["id"] = vid
    profile.setdefault("inheritsFrom", mc_version)
    write_json_atomic(version_json_path(paths, vid), profile)
    return vid


def loader_version_id(loader: str, mc_version: str, loader_version: str) -> str:
    if loader == "vanilla":
        return mc_version
    return f"{loader}-loader-{loader_version}-{mc_version}"
