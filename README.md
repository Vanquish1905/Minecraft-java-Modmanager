# Vanquish's Mod Manager

A lightweight, instance-based Minecraft: Java Edition launcher and mod manager in the spirit of
[Prism Launcher](https://prismlauncher.org/). It is written in pure Python with Tkinter and needs **no extra
packages**. It runs on **Windows, macOS and Linux**.

## Features

- **Instances**: each one is a separate game folder with its own version, mod loader, mods, resource packs,
  shader packs, worlds and settings. Instances can be grouped, copied, renamed and deleted, and play time is tracked.
- **Every Minecraft version** from Mojang's official manifest: releases, snapshots and old beta/alpha versions.
- **Fabric and Quilt** installed automatically. You pick the loader version or take the recommended one.
- **Built-in Modrinth browser** for mods, resource packs and shader packs. Results are filtered to your
  instance's version and loader, and required dependencies are installed too.
- **Mod updates**: "Check for updates" finds newer Modrinth versions of the mods you have installed.
- **Modpacks**: import `.mrpack` files, or search and install Modrinth modpacks directly.
- **Mod list** shows each mod's name, version and loader, read from the jar. Mods can be enabled or disabled
  (they are renamed to `.disabled`, as Prism does). The list warns about duplicate mods and mods built for another loader.
- **Java management**: finds installed Java, picks the right version for each Minecraft version (8, 17, 21 and so on)
  and downloads Eclipse Temurin automatically if none is suitable.
- **Accounts**: offline accounts, plus Microsoft accounts through device-code login (needs an Azure client ID).
- **Game log** in a live console, with world backups, world import from zip, and per-instance memory, JVM argument and Java settings.
- **Dark and light** themes.

Forge and NeoForge instances are not supported yet. Their installers need extra processing steps.

## Download

Get the latest version from the [Releases page](https://github.com/Vanquish1905/Minecraft-java-Modmanager/releases):

- **Windows:** `VanquishModManager.exe`. Double-click it; nothing needs to be installed.
- **Linux (portable):** unzip `VanquishModManager-<version>-linux-portable.zip` and run `./VanquishModManager`.
  All data stays in the `data` folder next to it.

You can also run it from source (below).

## Building the exe yourself

```bash
py -m pip install pyinstaller
py build.py
```

The result is `dist\VanquishModManager.exe`, with the app icon. On Linux, `python3 build.py --portable-zip`
also creates the portable zip. Pushing a tag like `v2.0.1` makes GitHub Actions build both and publish a release.

## Requirements

- Python **3.9 or newer** with Tkinter
  - Windows / macOS: the installer from [python.org](https://www.python.org/downloads/) includes Tk
  - Debian/Ubuntu: `sudo apt install python3 python3-tk`
  - Fedora: `sudo dnf install python3-tkinter`
  - Arch: `sudo pacman -S python tk`
  - macOS with Homebrew: `brew install python python-tk`
- Java is downloaded automatically when it is needed.

## Running

```bash
git clone https://github.com/vanquish1905/minecraft-java-modmanager.git
cd minecraft-java-modmanager
python3 main.py
```

On Windows, use `py main.py` or double-click `main.py`. You can also start it with `python3 -m vanquish`.

### First steps
1. Click your account button (top right), choose **Manage accounts** and add an account.
2. Click **+ Add Instance**, pick a version and optionally Fabric or Quilt, then click **Create**.
3. Select the instance and click **Mods**, then **Download mods** to install mods from Modrinth.
4. Click **Launch**.

### Keyboard shortcuts

| Action | Windows / Linux | macOS |
|--------|-----------------|-------|
| New instance | Ctrl+N | Cmd+N |
| Settings | Ctrl+, | Cmd+, |
| Filter instances | Ctrl+F | Cmd+F |
| Refresh | F5 | F5 |
| Select instance | Arrow keys | Arrow keys |
| Launch / delete selected | Enter / Delete | Enter / Delete |
| Quit | Ctrl+Q | Cmd+Q |

In lists, click a column heading to sort it. In the Mods tab, click the "On" column to turn a mod on or off.

## Where data is stored

| OS      | Folder |
|---------|--------|
| Windows | `%APPDATA%\VanquishModManager` |
| macOS   | `~/Library/Application Support/VanquishModManager` |
| Linux   | `~/.local/share/vanquish-modmanager` (or `$XDG_DATA_HOME`) |

To run in portable mode, create an empty `portable.txt` next to `main.py` and data is kept in `./data`.
You can also set the `VANQUISH_DATA_DIR` environment variable.
Your existing `.minecraft` folder is never modified. To bring old mods, configs and worlds into an instance,
use "Copy mods/config/worlds from folder" when you create it.

## Microsoft accounts

Logging in with Microsoft needs an Azure application (client) ID:

1. Go to portal.azure.com, then **App registrations**, then **New registration**. Choose
   "Personal Microsoft accounts only".
2. Under **Authentication**, enable **Allow public client flows**.
3. Paste the Application (client) ID into **Settings > Microsoft login**.

Mojang must approve new app IDs before they can access Minecraft services. Until yours is approved, you can
use an offline account. Offline mode works in singleplayer and on offline-mode servers.

## Project layout

```
main.py                 entry point
vanquish/
  platform_utils.py     OS detection, data folders, opening files
  net.py                HTTP + verified parallel downloads (urllib only)
  versions.py           Mojang manifests, rules, libraries, natives, assets
  loaders.py            Fabric / Quilt meta APIs
  java.py               Java detection and Temurin download
  accounts.py           offline + Microsoft accounts
  instances.py          instance storage
  mods.py               mod metadata, enable/disable
  modrinth.py           Modrinth search, install, updates
  mrpack.py             .mrpack import
  launch.py             building the Java command line and running the game
  gui/                  Tkinter interface
tests/                  unit + end-to-end tests (python3 -m unittest discover -s tests)
```

## What was wrong with the old version

The old single-file script (`Vanquish's Modmanager.py`) had several problems:

- It ran `pip install` on every start. That breaks on modern Linux and macOS Python installs (PEP 668).
- The saved Minecraft path was ignored and overwritten on every start. Settings lived inside `.minecraft`, so the
  app could not find them again, and a stray `~/.minecraft_temp` folder was created when nothing was detected.
- "Profiles" never changed which mods were active. Disabled mods were moved into a private folder.
- NeoForge was never detected, because `"forge" in "neoforge"` matched first.
- Mouse-wheel scrolling only worked on Windows. Linux uses Button-4/5 and macOS sends different wheel values.
- Fonts were hard-coded ("SF Pro Display" or "Ubuntu") and often missing, and the Linux launcher detection
  returned a command that usually didn't exist.
- The "popular mods" lists were static text with no downloads. Everything ran on the UI thread, so the window
  froze during downloads.
