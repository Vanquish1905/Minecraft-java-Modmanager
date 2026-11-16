## Vanquish's Mod Manager 2.0: the big rewrite

A completely rebuilt, instance-based Minecraft launcher and mod manager, inspired by Prism Launcher.

### Downloads
- **Windows:** `VanquishModManager.exe`. Download it and double-click to run; nothing to install.
  If SmartScreen warns you, click *More info*, then *Run anyway*.
- **Linux (portable):** `VanquishModManager-2.0.0-linux-portable.zip`. Unzip it and run `./VanquishModManager`.
  All data (instances, Java, settings) stays in the `data` folder next to it.

### What's new
- **Instances**: separate game folders, each with its own version, mod loader, mods, packs, worlds and settings
- **Every Minecraft version**, plus automatic **Fabric** and **Quilt** installation
- **Built-in Modrinth browser** for mods, resource packs and shaders, with dependency installs and update checks
- **Modpacks**: import `.mrpack` files or install Modrinth modpacks directly
- **Java handled for you**: finds installed Java, or downloads the right version automatically
- **Offline and Microsoft accounts**, a live game log, world backups and per-instance memory/Java settings
- Dark and light themes, keyboard shortcuts, sortable lists
- Works on **Windows, macOS and Linux**

### Fixed from 1.x
- The app no longer runs `pip install` on startup or freezes during downloads
- Settings are now saved properly
- NeoForge detection works
- Mouse scrolling works on Linux and macOS

Forge and NeoForge instances are not supported yet.
