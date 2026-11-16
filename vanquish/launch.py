"""Preparing an instance and building the Java command line that starts Minecraft."""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import threading
from pathlib import Path
from typing import Callable

from . import APP_ID, __version__, java, loaders, versions
from .accounts import Account
from .config import Paths, Settings
from .instances import Instance
from .platform_utils import IS_MAC, IS_WINDOWS


class LaunchError(Exception):
    pass


def ensure_installed(paths: Paths, inst: Instance, progress=None,
                     cancel: threading.Event | None = None, workers: int = 8, verify: bool = False) -> dict:
    """Download the loader profile and all game files the instance needs."""
    vid = inst.version_id
    if inst.loader != "vanilla":
        if not inst.loader_version:
            if progress:
                progress(f"Finding {inst.loader} version...", None)
            inst.loader_version = loaders.recommended_loader_version(inst.loader, inst.mc_version)
        expected = versions.version_json_path(paths, vid) if vid else None
        stale = not vid or not vid.startswith(f"{inst.loader}-") or \
            f"-{inst.loader_version}-" not in vid or not vid.endswith(f"-{inst.mc_version}")
        if stale or not expected.exists():
            if progress:
                progress(f"Installing {loaders.LOADER_LABELS[inst.loader]} {inst.loader_version}...", None)
            vid = loaders.install_loader_profile(paths, inst.loader, inst.mc_version, inst.loader_version)
    else:
        vid = inst.mc_version
    if vid != inst.version_id:
        inst.version_id = vid
        inst.save()
    return versions.install_version(paths, vid, progress, cancel, workers=workers, verify=verify)


def _substitute(arg: str, values: dict) -> str:
    return re.sub(r"\$\{([^}]+)\}", lambda m: str(values.get(m.group(1), m.group(0))), arg)


def _collect(args: list, features: dict) -> list[str]:
    out: list[str] = []
    for a in args:
        if isinstance(a, str):
            out.append(a)
            continue
        if not isinstance(a, dict) or not versions.rules_allow(a.get("rules"), features):
            continue
        val = a.get("value")
        if isinstance(val, list):
            out.extend(val)
        elif isinstance(val, str):
            out.append(val)
    return out


def build_command(paths: Paths, inst: Instance, version: dict, account: Account,
                  java_path: str, settings: Settings) -> list[str]:
    game_dir = inst.game_dir
    game_dir.mkdir(parents=True, exist_ok=True)
    width = inst.window_width or settings.window_width
    height = inst.window_height or settings.window_height
    features = {"has_custom_resolution": bool(width and height)}

    assets_root = paths.assets
    legacy = versions.prepare_legacy_assets(paths, version, game_dir)
    classpath = os.pathsep.join(versions.build_classpath(paths, version))
    values = {
        "auth_player_name": account.name,
        "version_name": version.get("id", inst.mc_version),
        "game_directory": str(game_dir),
        "assets_root": str(assets_root),
        "game_assets": str(legacy or assets_root),
        "assets_index_name": (version.get("assetIndex") or {}).get("id", version.get("assets", "")),
        "auth_uuid": account.uuid.replace("-", ""),
        "auth_access_token": account.access_token or "0",
        "auth_session": account.access_token or "0",
        "auth_xuid": account.xuid or "0",
        "clientid": "0",
        "user_type": "msa" if account.kind == "msa" else "legacy",
        "user_properties": "{}",
        "version_type": version.get("type", "release"),
        "natives_directory": str(inst.natives_dir),
        "launcher_name": APP_ID,
        "launcher_version": __version__,
        "classpath": classpath,
        "classpath_separator": os.pathsep,
        "library_directory": str(paths.libraries),
        "resolution_width": str(width),
        "resolution_height": str(height),
    }

    min_mem = inst.min_memory or settings.min_memory
    max_mem = inst.max_memory or settings.max_memory
    if min_mem > max_mem:
        min_mem = max_mem
    cmd = [java_path, f"-Xms{min_mem}M", f"-Xmx{max_mem}M"]

    extra = (inst.jvm_args or settings.jvm_args).strip()
    if extra:
        cmd += shlex.split(extra, posix=not IS_WINDOWS)

    arguments = version.get("arguments")
    if arguments and arguments.get("jvm"):
        jvm = _collect(arguments["jvm"], features)
    else:  # versions before 1.13 have no jvm argument list
        jvm = ["-Djava.library.path=${natives_directory}", "-cp", "${classpath}"]
        if IS_MAC:
            jvm.insert(0, "-XstartOnFirstThread")
        if IS_WINDOWS:
            jvm.insert(0, "-XX:HeapDumpPath=MojangTricksIntelDriversForPerformance_javaw.exe_minecraft.exe.heapdump")
    # LWJGL 3 extracts natives itself; keep them inside the instance.
    jvm.append(f"-Dorg.lwjgl.system.SharedLibraryExtractPath={inst.natives_dir}")
    jvm.append(f"-Djna.tmpdir={inst.natives_dir}")
    cmd += [_substitute(a, values) for a in jvm]

    log = versions.logging_config(paths, version)
    if log and log[0].exists():
        cmd.append(log[1].replace("${path}", str(log[0])))

    cmd.append(version["mainClass"])

    if arguments and arguments.get("game"):
        game = _collect(arguments["game"], features)
    else:
        game = (version.get("minecraftArguments") or "").split()
        if features["has_custom_resolution"]:
            game += ["--width", "${resolution_width}", "--height", "${resolution_height}"]
    cmd += [_substitute(a, values) for a in game]
    return cmd


def select_java(paths: Paths, inst: Instance, version: dict, settings: Settings,
                progress=None, cancel=None) -> str:
    required = versions.required_java(version)
    configured = inst.java_path or settings.java_path
    if configured:
        info = java.probe(configured)
        if not info:
            raise LaunchError(f"The configured Java does not run:\n{configured}")
        if info.major < required:
            raise LaunchError(f"Minecraft {inst.mc_version} needs Java {required}, but the configured "
                              f"Java is version {info.major}:\n{configured}\n\n"
                              "Clear the Java path in settings to pick one automatically.")
        return configured
    found = java.pick_java(required, paths)
    if found:
        return found.path
    if progress:
        progress(f"Java {required} not found - downloading it...", None)
    return java.download_java(paths, required, progress, cancel).path


def prepare(paths: Paths, inst: Instance, account: Account, settings: Settings,
            progress=None, cancel=None) -> list[str]:
    version = ensure_installed(paths, inst, progress, cancel, workers=settings.download_workers)
    if progress:
        progress("Extracting native libraries...", None)
    versions.extract_natives(paths, version, inst.natives_dir)
    java_path = select_java(paths, inst, version, settings, progress, cancel)
    return build_command(paths, inst, version, account, java_path, settings)


def start(cmd: list[str], cwd: Path, on_line: Callable[[str], None],
          on_exit: Callable[[int], None]) -> subprocess.Popen:
    kwargs = {}
    if IS_WINDOWS:
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True     # game keeps running if the launcher closes
    env = dict(os.environ)
    env.pop("_JAVA_OPTIONS", None)
    proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, env=env, **kwargs)

    def reader():
        assert proc.stdout is not None
        for raw in iter(proc.stdout.readline, b""):
            on_line(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
        proc.stdout.close()
        on_exit(proc.wait())

    threading.Thread(target=reader, daemon=True, name="game-log").start()
    return proc


def censor(cmd: list[str], account: Account) -> str:
    """Command line for the log, without the access token."""
    tok = account.access_token
    parts = ["<token>" if tok and tok != "0" and p == tok else p for p in cmd]
    return " ".join(shlex.quote(p) for p in parts)

