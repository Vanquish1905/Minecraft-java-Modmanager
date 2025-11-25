import json
import os
import platform
from pathlib import Path

class Config:
    def __init__(self):
        self.app_name = "Vanquish ModManager V2"
        self.version = "2.5.0"
        self.base_dir = Path.home() / ".vanquish_mm_v2"
        self.base_dir.mkdir(exist_ok=True)
        self.settings_file = self.base_dir / "settings.json"
        self.cache_dir = self.base_dir / "cache"
        self.cache_dir.mkdir(exist_ok=True)
        self.profiles_dir = self.base_dir / "profiles"
        self.profiles_dir.mkdir(exist_ok=True)
        self.backups_dir = self.base_dir / "backups"
        self.backups_dir.mkdir(exist_ok=True)
        self.defaults = {
            "minecraft_path": self._detect_mc_path(),
            "appearance_mode": "Dark",
            "color_theme": "blue",
            "ui_scale": 1.0,
            "auto_backup": True,
            "max_concurrent_downloads": 3
        }
        self.settings = self.load_settings()

    def _detect_mc_path(self):
        sys_name = platform.system()
        if sys_name == "Windows":
            p = Path(os.environ["APPDATA"]) / ".minecraft"
        elif sys_name == "Darwin":
            p = Path.home() / "Library" / "Application Support" / "minecraft"
        else:
            p = Path.home() / ".minecraft"
        return str(p) if p.exists() else ""

    def load_settings(self):
        if not self.settings_file.exists():
            return self.defaults.copy()
        try:
            with open(self.settings_file, "r") as f:
                data = json.load(f)
                for k, v in self.defaults.items():
                    if k not in data:
                        data[k] = v
                return data
        except:
            return self.defaults.copy()

    def save_settings(self):
        with open(self.settings_file, "w") as f:
            json.dump(self.settings, f, indent=4)

    def get(self, key):
        return self.settings.get(key, self.defaults.get(key))

    def set(self, key, value):
        self.settings[key] = value
        self.save_settings()