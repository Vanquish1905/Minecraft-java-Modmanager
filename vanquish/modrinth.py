"""Modrinth API client: search, install with dependencies, and update checks."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import net
from .mods import DISABLED_SUFFIX

API = os.environ.get("VANQUISH_MODRINTH_API", "https://api.modrinth.com/v2")

PROJECT_TYPES = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}


@dataclass
class SearchHit:
    project_id: str
    slug: str
    title: str
    author: str
    description: str
    downloads: int
    project_type: str
    categories: list = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"https://modrinth.com/{self.project_type}/{self.slug}"


def search(query: str, project_type: str = "mod", mc_version: str = "", loader: str = "",
           offset: int = 0, limit: int = 30, sort: str = "relevance") -> tuple[list[SearchHit], int]:
    facets = [[f"project_type:{project_type}"]]
    if mc_version:
        facets.append([f"versions:{mc_version}"])
    if loader and project_type == "mod" and loader != "vanilla":
        cats = [f"categories:{loader}"]
        if loader == "quilt":
            cats.append("categories:fabric")
        facets.append(cats)
    data = net.get_json(f"{API}/search", {"query": query, "facets": json.dumps(facets),
                                          "offset": offset, "limit": limit, "index": sort})
    hits = [SearchHit(h["project_id"], h.get("slug", ""), h.get("title", ""), h.get("author", ""),
                      h.get("description", ""), int(h.get("downloads", 0)),
                      h.get("project_type", project_type), h.get("categories", []))
            for h in data.get("hits", [])]
    return hits, int(data.get("total_hits", len(hits)))


def _loaders_for(project_type: str, loader: str) -> list[str]:
    if project_type != "mod" or not loader or loader == "vanilla":
        return []
    return ["quilt", "fabric"] if loader == "quilt" else [loader]


def project_versions(project_id: str, mc_version: str = "", loader: str = "",
                     project_type: str = "mod") -> list[dict]:
    params = {}
    lds = _loaders_for(project_type, loader)
    if lds:
        params["loaders"] = json.dumps(lds)
    if mc_version:
        params["game_versions"] = json.dumps([mc_version])
    return net.get_json(f"{API}/project/{project_id}/version", params or None)


def get_version(version_id: str) -> dict:
    return net.get_json(f"{API}/version/{version_id}")


def get_project(project_id: str) -> dict:
    return net.get_json(f"{API}/project/{project_id}")


def primary_file(version: dict) -> dict:
    files = version.get("files") or []
    if not files:
        raise ValueError(f"Version {version.get('name')} has no files")
    for f in files:
        if f.get("primary"):
            return f
    return files[0]


def best_version(project_id: str, mc_version: str, loader: str, project_type: str = "mod") -> Optional[dict]:
    vs = project_versions(project_id, mc_version, loader, project_type)
    if not vs:
        return None
    for v in vs:  # prefer stable releases
        if v.get("version_type") == "release":
            return v
    return vs[0]


def _installed_ids(folder: Path) -> set[str]:
    """Filenames present in a folder (enabled or disabled)."""
    if not folder.is_dir():
        return set()
    names = set()
    for p in folder.iterdir():
        n = p.name
        names.add(n[:-len(DISABLED_SUFFIX)] if n.endswith(DISABLED_SUFFIX) else n)
    return names


def install(project_id: str, game_dir: Path, mc_version: str, loader: str,
            project_type: str = "mod", version: dict | None = None, progress=None,
            with_dependencies: bool = True) -> list[str]:
    """Install a project (and its required dependencies). Returns installed file names."""
    folder = game_dir / PROJECT_TYPES.get(project_type, "mods")
    installed: list[str] = []
    visited: set[str] = set()
    existing = _installed_ids(folder)

    def do(pid: str, ver: dict | None, depth: int):
        if pid in visited or depth > 8:
            return
        visited.add(pid)
        if ver is None:
            ver = best_version(pid, mc_version, loader, project_type)
            if ver is None:
                raise ValueError(f"No compatible version of '{pid}' for {mc_version} {loader}")
        f = primary_file(ver)
        fname = os.path.basename(f["filename"])
        if fname not in existing:
            if progress:
                progress(f"Downloading {fname}...", None)
            net.download(f["url"], folder / fname, sha1=(f.get("hashes") or {}).get("sha1"))
            existing.add(fname)
            installed.append(fname)
        if not with_dependencies:
            return
        for dep in ver.get("dependencies") or []:
            if dep.get("dependency_type") != "required":
                continue
            dpid = dep.get("project_id")
            dver = None
            if dep.get("version_id"):
                try:
                    dver = get_version(dep["version_id"])
                    dpid = dpid or dver.get("project_id")
                except net.NetworkError:
                    dver = None
            if dpid:
                do(dpid, dver, depth + 1)

    do(project_id, version, 0)
    return installed


def check_updates(files: list[Path], mc_version: str, loader: str) -> dict[Path, dict]:
    """Returns {file: newer_version} for files that Modrinth knows a newer version of."""
    by_hash = {}
    for p in files:
        try:
            by_hash[net.sha1_of(p)] = p
        except OSError:
            pass
    if not by_hash:
        return {}
    payload = {"hashes": list(by_hash), "algorithm": "sha1", "game_versions": [mc_version]}
    lds = _loaders_for("mod", loader)
    if lds:
        payload["loaders"] = lds
    result = net.post_json(f"{API}/version_files/update", payload) or {}
    updates = {}
    for h, ver in result.items():
        p = by_hash.get(h)
        if p is None:
            continue
        files_hashes = {(f.get("hashes") or {}).get("sha1") for f in ver.get("files", [])}
        if h not in files_hashes:
            updates[p] = ver
    return updates


def apply_update(old: Path, version: dict) -> Path:
    f = primary_file(version)
    disabled = old.name.endswith(DISABLED_SUFFIX)
    name = os.path.basename(f["filename"]) + (DISABLED_SUFFIX if disabled else "")
    dest = old.with_name(name)
    net.download(f["url"], dest, sha1=(f.get("hashes") or {}).get("sha1"))
    if dest.resolve() != old.resolve():
        old.unlink(missing_ok=True)
    return dest
