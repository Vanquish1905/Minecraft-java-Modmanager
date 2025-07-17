import os
import sys
import json
import zipfile
import shutil
import logging
import platform
import threading
import webbrowser
import subprocess
import urllib.request
import urllib.parse
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, colorchooser, simpledialog
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import configparser
import base64
import uuid

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFilter, ImageEnhance
    import requests
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Hide console window on Windows
if platform.system() == "Windows":
    import ctypes
    ctypes.windll.kernel32.SetConsoleTitleW("Minecraft Mod Manager")
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd != 0:
        ctypes.windll.user32.ShowWindow(hwnd, 0)

@dataclass
class ModInfo:
    name: str
    version: str
    loader: str
    file_path: str
    enabled: bool = True
    description: str = ""
    minecraft_version: str = "Unknown"
    profile: str = "default"

@dataclass
class ModProfile:
    name: str
    description: str
    minecraft_version: str
    mod_loader: str
    mods: List[str]
    created_date: str
    last_used: str = ""

@dataclass
class ColorScheme:
    primary: str = "#2563eb"
    secondary: str = "#3b82f6"
    background: str = "#0f172a"
    surface: str = "#1e293b"
    text: str = "#f8fafc"
    accent: str = "#60a5fa"
    error: str = "#ef4444"
    success: str = "#10b981"
    warning: str = "#f59e0b"

@dataclass
class Settings:
    minecraft_path: str = ""
    theme: str = "modern"
    auto_detect: bool = True
    current_profile: str = "default"
    window_geometry: str = "1400x900"
    skin_username: str = ""
    color_scheme: ColorScheme = None
    animations_enabled: bool = True
    auto_backup: bool = True
    check_updates: bool = True
    launcher_path: str = ""
    debug_mode: bool = False
    
    def __post_init__(self):
        if self.color_scheme is None:
            self.color_scheme = ColorScheme()

class PopularModsData:
    POPULAR_MODS = [
        {"name": "JEI (Just Enough Items)", "loader": "Forge/Fabric", "category": "Utility", "description": "Recipe viewing and item management"},
        {"name": "OptiFine", "loader": "Forge", "category": "Performance", "description": "Graphics optimization and shaders"},
        {"name": "Sodium", "loader": "Fabric", "category": "Performance", "description": "Modern rendering engine"},
        {"name": "Lithium", "loader": "Fabric", "category": "Performance", "description": "Server-side optimization"},
        {"name": "Phosphor", "loader": "Fabric", "category": "Performance", "description": "Lighting engine optimization"},
        {"name": "Iris Shaders", "loader": "Fabric", "category": "Graphics", "description": "Shader support for Fabric"},
        {"name": "Iron Chests", "loader": "Forge/Fabric", "category": "Storage", "description": "Additional chest types"},
        {"name": "Waystones", "loader": "Forge/Fabric", "category": "Transportation", "description": "Fast travel waypoints"},
        {"name": "Biomes O' Plenty", "loader": "Forge", "category": "World Generation", "description": "Additional biomes"},
        {"name": "Tinkers' Construct", "loader": "Forge", "category": "Tools & Weapons", "description": "Customizable tools"},
        {"name": "Applied Energistics 2", "loader": "Forge", "category": "Technology", "description": "Advanced storage system"},
        {"name": "Thermal Expansion", "loader": "Forge", "category": "Technology", "description": "Industrial machinery"},
        {"name": "Botania", "loader": "Forge/Fabric", "category": "Magic", "description": "Nature-based magic mod"},
        {"name": "Create", "loader": "Forge", "category": "Technology", "description": "Mechanical contraptions"},
        {"name": "Twilight Forest", "loader": "Forge", "category": "Adventure", "description": "Magical dimension"},
        {"name": "JourneyMap", "loader": "Forge/Fabric", "category": "Utility", "description": "Real-time mapping"},
        {"name": "Mouse Tweaks", "loader": "Forge/Fabric", "category": "Utility", "description": "Inventory management"},
        {"name": "Quark", "loader": "Forge", "category": "Miscellaneous", "description": "Quality of life improvements"},
        {"name": "Storage Drawers", "loader": "Forge/Fabric", "category": "Storage", "description": "Compact item storage"},
        {"name": "Refined Storage", "loader": "Forge", "category": "Storage", "description": "Digital storage system"}
    ]
    
    POPULAR_MODPACKS = [
        {"name": "All the Mods 9", "category": "Kitchen Sink", "description": "Latest kitchen sink modpack"},
        {"name": "FTB Infinity Evolved", "category": "Expert", "description": "Classic expert mode pack"},
        {"name": "SkyFactory 4", "category": "Skyblock", "description": "Sky-based progression"},
        {"name": "Enigmatica 6", "category": "Kitchen Sink", "description": "Guided progression pack"},
        {"name": "RLCraft", "category": "Adventure", "description": "Hardcore survival experience"},
        {"name": "Valhelsia 5", "category": "Kitchen Sink", "description": "Modern kitchen sink pack"},
        {"name": "Better Minecraft", "category": "Adventure", "description": "Enhanced vanilla experience"},
        {"name": "Create: Above and Beyond", "category": "Expert", "description": "Create-focused expert pack"},
        {"name": "Stoneblock 3", "category": "Skyblock", "description": "Underground skyblock"},
        {"name": "Direwolf20 1.19", "category": "Tech", "description": "Tech-focused modpack"}
    ]

class VanquishModManager:
    def __init__(self, minecraft_path: str):
        self.minecraft_path = Path(minecraft_path)
        self.manager_path = self.minecraft_path / "modmanager_by_vanquish"
        self.manager_path.mkdir(exist_ok=True)
        
        # Create subdirectories
        self.profiles_path = self.manager_path / "profiles"
        self.profiles_path.mkdir(exist_ok=True)
        
        self.disabled_mods_path = self.manager_path / "disabled_mods"
        self.disabled_mods_path.mkdir(exist_ok=True)
        
        self.modpacks_path = self.manager_path / "modpacks"
        self.modpacks_path.mkdir(exist_ok=True)
        
        self.skins_path = self.manager_path / "skins"
        self.skins_path.mkdir(exist_ok=True)
        
        self.backups_path = self.manager_path / "backups"
        self.backups_path.mkdir(exist_ok=True)
        
        self.settings_file = self.manager_path / "settings.json"
        self.log_file = self.manager_path / "modmanager.log"
        
        # Standard Minecraft paths
        self.mods_path = self.minecraft_path / "mods"
        self.mods_path.mkdir(exist_ok=True)
        self.resource_packs_path = self.minecraft_path / "resourcepacks"
        self.resource_packs_path.mkdir(exist_ok=True)

class AnimatedWidget:
    def __init__(self, widget, duration=300):
        self.widget = widget
        self.duration = duration
        self.animation_id = None
        
    def fade_in(self, callback=None):
        if not hasattr(self.widget, 'winfo_exists') or not self.widget.winfo_exists():
            return
            
        steps = 20
        step_time = self.duration // steps
        
        def animate_step(step):
            if step <= steps and self.widget.winfo_exists():
                alpha = step / steps
                try:
                    if hasattr(self.widget, 'configure'):
                        current_bg = self.widget.cget('bg') if 'bg' in self.widget.keys() else None
                        if current_bg:
                            self.widget.configure(bg=current_bg)
                except:
                    pass
                
                if step < steps:
                    self.animation_id = self.widget.after(step_time, lambda: animate_step(step + 1))
                elif callback:
                    callback()
        
        animate_step(0)

class ModernButton(tk.Canvas):
    def __init__(self, parent, text, command=None, width=120, height=35,
                 bg_color="#2563eb", hover_color="#3b82f6", text_color="white",
                 corner_radius=12, shadow=True, **kwargs):
        super().__init__(parent, width=width, height=height, highlightthickness=0, **kwargs)

        self.command = command
        self.text = text
        self.width = width
        self.height = height
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.text_color = text_color
        self.corner_radius = corner_radius
        self.shadow = shadow

        self.is_hovered = False
        self.is_pressed = False
        self.is_disabled = False

        self.bind("<Button-1>", self.on_click)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)

        self.draw_button()

    def draw_button(self):
        self.delete("all")

        if self.is_disabled:
            color = "#64748b"  # Darker grey for disabled background
            text_color = "#dddddd" # Light grey text for disabled state
            text_bg_color = "#344054" # A darker background for disabled text, ensuring contrast
        elif self.is_pressed:
            color = self.darken_color(self.bg_color, 0.8)
            text_color = self.text_color
            text_bg_color = self.darken_color(color, 0.5) # Darker text background on press
        elif self.is_hovered:
            color = self.hover_color
            text_color = self.text_color
            text_bg_color = self.darken_color(color, 0.5) # Darker text background on hover
        else:
            color = self.bg_color
            text_color = self.text_color
            text_bg_color = self.darken_color(color, 0.5) # Default dark background for text

        # Draw shadow
        if self.shadow and not self.is_disabled:
            shadow_color = self.darken_color(color, 0.3)
            self.create_rounded_rect(4, 4, self.width, self.height,
                                   self.corner_radius, fill=shadow_color, outline="")

        # Draw main button
        self.create_rounded_rect(2, 2, self.width-2, self.height-2,
                                self.corner_radius, fill=color, outline="")

        # Add gradient effect
        if not self.is_disabled:
            gradient_color = self.lighten_color(color, 1.2)
            self.create_rounded_rect(2, 2, self.width-2, self.height//3,
                                   self.corner_radius, fill=gradient_color, outline="")

        # Determine font properties
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        font_size = 9 if len(self.text) > 15 else 10
        font_weight = "bold"
        button_font = (font_family, font_size, font_weight)

        text_x = self.width // 2
        text_y = self.height // 2

        # Create a temporary text item to measure its bounding box
        temp_text_item = self.create_text(text_x, text_y, text=self.text, font=button_font, anchor="center")
        bbox = self.bbox(temp_text_item) # Get the bounding box of the text
        self.delete(temp_text_item) # Delete the temporary item

        # Calculate padding for the background rectangle
        padding_x = 10 # Horizontal padding
        padding_y = 6  # Vertical padding

        # Draw the semi-transparent background rectangle for the text
        # Adjust coordinates to ensure it's centered around the text
        if bbox:
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            rect_x1 = text_x - (text_width / 2) - padding_x
            rect_y1 = text_y - (text_height / 2) - padding_y
            rect_x2 = text_x + (text_width / 2) + padding_x
            rect_y2 = text_y + (text_height / 2) + padding_y

            # Ensure the text background rectangle fits within the button
            rect_x1 = max(2, rect_x1)
            rect_y1 = max(2, rect_y1)
            rect_x2 = min(self.width - 2, rect_x2)
            rect_y2 = min(self.height - 2, rect_y2)

            self.create_rounded_rect(rect_x1, rect_y1, rect_x2, rect_y2,
                                     radius=self.corner_radius // 2, # Smaller radius for text background
                                     fill=text_bg_color, outline="")

        # Draw the actual text on top
        self.create_text(text_x, text_y, text=self.text,
                        fill=text_color, font=button_font,
                        anchor="center")


    def create_rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = []
        # Ensure radius doesn't exceed half of the smaller dimension
        radius = min(radius, abs(x2 - x1) / 2, abs(y2 - y1) / 2)

        # Top left corner
        points.extend([x1 + radius, y1, x1, y1, x1, y1 + radius])
        # Top right corner
        points.extend([x2 - radius, y1, x2, y1, x2, y1 + radius])
        # Bottom right corner
        points.extend([x2, y2 - radius, x2, y2, x2 - radius, y2])
        # Bottom left corner
        points.extend([x1 + radius, y2, x1, y2, x1, y2 - radius])

        return self.create_polygon(points, smooth=True, **kwargs)

    def lighten_color(self, color, factor):
        try:
            color = color.lstrip('#')
            rgb = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
            rgb = tuple(min(255, int(c * factor)) for c in rgb)
            return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        except ValueError:
            return color

    def darken_color(self, color, factor):
        try:
            color = color.lstrip('#')
            rgb = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
            rgb = tuple(int(c * factor) for c in rgb)
            return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        except ValueError:
            return color

    def on_click(self, event):
        if not self.is_disabled:
            self.is_pressed = True
            self.draw_button()

    def on_release(self, event):
        if not self.is_disabled:
            self.is_pressed = False
            self.draw_button()
            if self.command:
                self.command()

    def on_enter(self, event):
        if not self.is_disabled:
            self.is_hovered = True
            self.draw_button()

    def on_leave(self, event):
        self.is_hovered = False
        self.draw_button()

    def set_disabled(self, disabled):
        self.is_disabled = disabled
        self.draw_button()


class GradientFrame(tk.Canvas):
    def __init__(self, parent, width, height, color1, color2, direction='vertical', **kwargs):
        super().__init__(parent, width=width, height=height, highlightthickness=0, **kwargs)
        self.width = width
        self.height = height
        self.color1 = color1
        self.color2 = color2
        self.direction = direction
        
        self.bind('<Configure>', self.on_configure)
        self.draw_gradient()
    
    def draw_gradient(self):
        self.delete("gradient")
        
        if self.direction == 'vertical':
            for i in range(self.height):
                ratio = i / self.height
                color = self.interpolate_color(self.color1, self.color2, ratio)
                self.create_line(0, i, self.width, i, fill=color, tags="gradient")
        else:
            for i in range(self.width):
                ratio = i / self.width
                color = self.interpolate_color(self.color1, self.color2, ratio)
                self.create_line(i, 0, i, self.height, fill=color, tags="gradient")
    
    def interpolate_color(self, color1, color2, ratio):
        try:
            c1 = color1.lstrip('#')
            c2 = color2.lstrip('#')
            
            rgb1 = tuple(int(c1[i:i+2], 16) for i in (0, 2, 4))
            rgb2 = tuple(int(c2[i:i+2], 16) for i in (0, 2, 4))
            
            rgb = tuple(int(rgb1[i] + (rgb2[i] - rgb1[i]) * ratio) for i in range(3))
            return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        except:
            return color1
    
    def on_configure(self, event):
        self.width = event.width
        self.height = event.height
        self.draw_gradient()

class ModernStyle:
    def __init__(self, root, theme="modern"):
        self.root = root
        self.theme = theme
        self.style = ttk.Style()
        self.setup_theme()
    
    def setup_theme(self):
        if self.theme == "modern":
            self.setup_modern_theme()
        elif self.theme == "dark":
            self.setup_dark_theme()
        else:
            self.setup_light_theme()
    
    def setup_modern_theme(self):
        """New sleek modern theme with better text rendering"""
        self.root.configure(bg='#0f172a')
        
        self.style.theme_use('clam')
        
        self.colors = {
            'bg': '#0f172a',
            'fg': '#f8fafc',
            'select_bg': '#1e293b',
            'select_fg': '#f8fafc',
            'button_bg': '#2563eb',
            'button_fg': '#ffffff',
            'entry_bg': '#1e293b',
            'entry_fg': '#f8fafc',
            'frame_bg': '#1e293b',
            'accent': '#3b82f6',
            'success': '#10b981',
            'error': '#ef4444',
            'warning': '#f59e0b'
        }
        
        self.apply_colors()
    
    def setup_dark_theme(self):
        self.root.configure(bg='#1e1e1e')
        
        self.style.theme_use('clam')
        
        self.colors = {
            'bg': '#1e1e1e',
            'fg': '#ffffff',
            'select_bg': '#404040',
            'select_fg': '#ffffff',
            'button_bg': '#3d6b47',
            'button_fg': '#ffffff',
            'entry_bg': '#2d2d2d',
            'entry_fg': '#ffffff',
            'frame_bg': '#2a2a2a',
            'accent': '#4a7c59'
        }
        
        self.apply_colors()
    
    def setup_light_theme(self):
        self.root.configure(bg='#f8fafc')
        
        self.style.theme_use('clam')
        
        self.colors = {
            'bg': '#f8fafc',
            'fg': '#1e293b',
            'select_bg': '#e2e8f0',
            'select_fg': '#1e293b',
            'button_bg': '#2563eb',
            'button_fg': '#ffffff',
            'entry_bg': '#ffffff',
            'entry_fg': '#1e293b',
            'frame_bg': '#ffffff',
            'accent': '#3b82f6'
        }
        
        self.apply_colors()
    
    def apply_colors(self):
        # Enhanced font settings for better readability
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        self.style.configure('TFrame', background=self.colors['frame_bg'])
        self.style.configure('TLabel', background=self.colors['frame_bg'], foreground=self.colors['fg'], 
                           font=(font_family, 10))
        self.style.configure('TButton', background=self.colors['button_bg'], foreground=self.colors['button_fg'],
                           font=(font_family, 10, "bold"))
        self.style.map('TButton', background=[('active', self.colors['accent'])])
        self.style.configure('TEntry', background=self.colors['entry_bg'], foreground=self.colors['entry_fg'], 
                           fieldbackground=self.colors['entry_bg'], font=(font_family, 10))
        self.style.configure('TText', background=self.colors['entry_bg'], foreground=self.colors['entry_fg'],
                           font=(font_family, 10))
        self.style.configure('TCheckbutton', background=self.colors['frame_bg'], foreground=self.colors['fg'],
                           font=(font_family, 10))
        self.style.configure('TRadiobutton', background=self.colors['frame_bg'], foreground=self.colors['fg'],
                           font=(font_family, 10))
        self.style.configure('Treeview', background=self.colors['entry_bg'], foreground=self.colors['fg'], 
                           fieldbackground=self.colors['entry_bg'], font=(font_family, 10))
        self.style.configure('Treeview.Heading', background=self.colors['select_bg'], foreground=self.colors['fg'],
                           font=(font_family, 10, "bold"))
        self.style.configure('TCombobox', background=self.colors['entry_bg'], foreground=self.colors['entry_fg'], 
                           fieldbackground=self.colors['entry_bg'], font=(font_family, 10))
        self.style.configure('TLabelFrame', background=self.colors['frame_bg'], foreground=self.colors['fg'])
        self.style.configure('TLabelFrame.Label', background=self.colors['frame_bg'], foreground=self.colors['fg'],
                           font=(font_family, 11, "bold"))

class MinecraftDetector:
    @staticmethod
    def get_default_minecraft_paths() -> List[str]:
        system = platform.system()
        home = Path.home()
        
        paths = []
        if system == "Windows":
            paths = [
                home / "AppData" / "Roaming" / ".minecraft",
                home / "AppData" / "Local" / "Packages" / "Microsoft.MinecraftUWP_8wekyb3d8bbwe" / "LocalState" / "games" / "com.mojang",
                Path("C:") / "Users" / os.getenv("USERNAME", "") / "AppData" / "Roaming" / ".minecraft"
            ]
        elif system == "Darwin":  # macOS
            paths = [
                home / "Library" / "Application Support" / "minecraft"
            ]
        else:  # Linux
            paths = [
                home / ".minecraft"
            ]
        
        # Add some additional common paths
        if system == "Windows":
            paths.extend([
                home / "Documents" / "MultiMC" / "instances",
                home / "AppData" / "Local" / "ATLauncher" / "instances",
                Path("C:") / "MultiMC" / "instances"
            ])
        
        return [str(p) for p in paths if p.exists()]
    
    @staticmethod
    def detect_minecraft() -> Optional[str]:
        paths = MinecraftDetector.get_default_minecraft_paths()
        
        for path in paths:
            path_obj = Path(path)
            
            # Check for standard .minecraft structure
            if (path_obj / "versions").exists():
                return str(path_obj)
        
        return None
    
    @staticmethod
    def get_minecraft_versions(minecraft_path: str) -> List[str]:
        versions = []
        versions_path = Path(minecraft_path) / "versions"
        
        if not versions_path.exists():
            return versions
        
        try:
            for version_dir in versions_path.iterdir():
                if version_dir.is_dir():
                    json_file = version_dir / f"{version_dir.name}.json"
                    jar_file = version_dir / f"{version_dir.name}.jar"
                    
                    if json_file.exists() or jar_file.exists():
                        versions.append(version_dir.name)
        except Exception as e:
            logging.error(f"Error getting Minecraft versions: {e}")
        
        return sorted(versions, reverse=True)
    
    @staticmethod
    def detect_mod_loaders(minecraft_path: str) -> Dict[str, List[str]]:
        """Detect installed mod loaders"""
        path = Path(minecraft_path)
        loaders = {
            "fabric": [],
            "forge": [],
            "quilt": [],
            "neoforge": []
        }
        
        versions_path = path / "versions"
        if not versions_path.exists():
            return loaders
        
        try:
            for version_dir in versions_path.iterdir():
                if version_dir.is_dir():
                    version_name = version_dir.name.lower()
                    if "fabric" in version_name:
                        loaders["fabric"].append(version_dir.name)
                    elif "forge" in version_name:
                        loaders["forge"].append(version_dir.name)
                    elif "quilt" in version_name:
                        loaders["quilt"].append(version_dir.name)
                    elif "neoforge" in version_name:
                        loaders["neoforge"].append(version_dir.name)
        except Exception as e:
            logging.error(f"Error detecting mod loaders: {e}")
        
        return loaders
    
    @staticmethod
    def detect_launcher_path() -> Optional[str]:
        system = platform.system()
        
        if system == "Windows":
            # Check for Minecraft Launcher
            launcher_paths = [
                Path(os.environ.get('LOCALAPPDATA', '')) / "Packages" / "Microsoft.4297127D64EC6_8wekyb3d8bbwe" / "LocalCache" / "Local" / "game" / "Minecraft Launcher.exe",
                Path("C:") / "Program Files (x86)" / "Minecraft Launcher" / "MinecraftLauncher.exe",
                Path("C:") / "Program Files" / "Minecraft Launcher" / "MinecraftLauncher.exe"
            ]
            
            for path in launcher_paths:
                if path.exists():
                    return str(path)
        
        elif system == "Darwin":  # macOS
            launcher_path = Path("/Applications/Minecraft.app")
            if launcher_path.exists():
                return str(launcher_path)
        
        else:  # Linux
            # Check common Linux launcher locations
            launcher_paths = [
                Path.home() / ".local" / "share" / "applications" / "minecraft-launcher.desktop",
                Path("/usr/share/applications/minecraft-launcher.desktop")
            ]
            
            for path in launcher_paths:
                if path.exists():
                    return "minecraft-launcher"
        
        return None

class ProfileManager:
    def __init__(self, manager_path: Path):
        self.profiles_path = manager_path / "profiles"
        self.profiles_path.mkdir(exist_ok=True)
        self.current_profile = "default"
        
        # Create default profile if it doesn't exist
        default_profile_file = self.profiles_path / "default.json"
        if not default_profile_file.exists():
            default_profile = ModProfile(
                name="Default",
                description="Default mod profile",
                minecraft_version="Latest",
                mod_loader="Any",
                mods=[],
                created_date=datetime.now().isoformat()
            )
            self.save_profile(default_profile)
    
    def get_profiles(self) -> List[ModProfile]:
        profiles = []
        try:
            for profile_file in self.profiles_path.glob("*.json"):
                with open(profile_file, 'r') as f:
                    data = json.load(f)
                    profile = ModProfile(**data)
                    profiles.append(profile)
        except Exception as e:
            logging.error(f"Error loading profiles: {e}")
        
        return sorted(profiles, key=lambda p: p.name)
    
    def save_profile(self, profile: ModProfile):
        try:
            profile_file = self.profiles_path / f"{profile.name.lower().replace(' ', '_')}.json"
            with open(profile_file, 'w') as f:
                json.dump(asdict(profile), f, indent=2)
        except Exception as e:
            logging.error(f"Error saving profile: {e}")
    
    def delete_profile(self, profile_name: str):
        try:
            profile_file = self.profiles_path / f"{profile_name.lower().replace(' ', '_')}.json"
            if profile_file.exists():
                profile_file.unlink()
        except Exception as e:
            logging.error(f"Error deleting profile: {e}")
    
    def get_profile(self, profile_name: str) -> Optional[ModProfile]:
        try:
            profile_file = self.profiles_path / f"{profile_name.lower().replace(' ', '_')}.json"
            if profile_file.exists():
                with open(profile_file, 'r') as f:
                    data = json.load(f)
                    return ModProfile(**data)
        except Exception as e:
            logging.error(f"Error loading profile: {e}")
        return None

class ModManager:
    def __init__(self, vanquish_manager: VanquishModManager):
        self.vm = vanquish_manager
        self.profile_manager = ProfileManager(self.vm.manager_path)
    
    def get_installed_mods(self, profile: str = "default") -> List[ModInfo]:
        mods = []
        if not self.vm.mods_path.exists():
            return mods
        
        try:
            # Get enabled mods
            for mod_file in self.vm.mods_path.glob("*.jar"):
                if mod_file.is_file():
                    mod_info = ModInfo(
                        name=mod_file.stem,
                        version=self.extract_mod_version(mod_file),
                        loader=self.detect_mod_loader(mod_file),
                        file_path=str(mod_file),
                        enabled=True,
                        minecraft_version=self.detect_mod_minecraft_version(mod_file),
                        profile=profile,
                        description=self.extract_mod_description(mod_file)
                    )
                    mods.append(mod_info)
            
            # Get disabled mods
            for mod_file in self.vm.disabled_mods_path.glob("*.jar"):
                if mod_file.is_file():
                    mod_info = ModInfo(
                        name=mod_file.stem,
                        version=self.extract_mod_version(mod_file),
                        loader=self.detect_mod_loader(mod_file),
                        file_path=str(mod_file),
                        enabled=False,
                        minecraft_version=self.detect_mod_minecraft_version(mod_file),
                        profile=profile,
                        description=self.extract_mod_description(mod_file)
                    )
                    mods.append(mod_info)
                    
        except Exception as e:
            logging.error(f"Error getting installed mods: {e}")
        
        return mods
    
    def extract_mod_version(self, mod_file: Path) -> str:
        try:
            with zipfile.ZipFile(mod_file, 'r') as zip_file:
                # Try fabric.mod.json first
                if 'fabric.mod.json' in zip_file.namelist():
                    fabric_info = json.loads(zip_file.read('fabric.mod.json').decode('utf-8'))
                    return fabric_info.get('version', 'Unknown')
                
                # Try mcmod.info for Forge
                elif 'mcmod.info' in zip_file.namelist():
                    mcmod_info = json.loads(zip_file.read('mcmod.info').decode('utf-8'))
                    if isinstance(mcmod_info, list) and len(mcmod_info) > 0:
                        return mcmod_info[0].get('version', 'Unknown')
                
                # Try META-INF/mods.toml for newer Forge
                elif 'META-INF/mods.toml' in zip_file.namelist():
                    toml_content = zip_file.read('META-INF/mods.toml').decode('utf-8')
                    for line in toml_content.split('\n'):
                        if line.strip().startswith('version='):
                            return line.split('=')[1].strip().strip('"\'')
        except Exception:
            pass
        return "Unknown"
    
    def extract_mod_description(self, mod_file: Path) -> str:
        try:
            with zipfile.ZipFile(mod_file, 'r') as zip_file:
                if 'fabric.mod.json' in zip_file.namelist():
                    fabric_info = json.loads(zip_file.read('fabric.mod.json').decode('utf-8'))
                    return fabric_info.get('description', '')
                
                elif 'mcmod.info' in zip_file.namelist():
                    mcmod_info = json.loads(zip_file.read('mcmod.info').decode('utf-8'))
                    if isinstance(mcmod_info, list) and len(mcmod_info) > 0:
                        return mcmod_info[0].get('description', '')
        except Exception:
            pass
        return ""
    
    def detect_mod_loader(self, mod_file: Path) -> str:
        try:
            with zipfile.ZipFile(mod_file, 'r') as zip_file:
                if 'fabric.mod.json' in zip_file.namelist():
                    return "Fabric"
                elif 'mcmod.info' in zip_file.namelist():
                    return "Forge"
                elif 'META-INF/mods.toml' in zip_file.namelist():
                    return "Forge"
                elif 'quilt.mod.json' in zip_file.namelist():
                    return "Quilt"
        except Exception:
            pass
        return "Unknown"
    
    def detect_mod_minecraft_version(self, mod_file: Path) -> str:
        try:
            with zipfile.ZipFile(mod_file, 'r') as zip_file:
                if 'fabric.mod.json' in zip_file.namelist():
                    fabric_info = json.loads(zip_file.read('fabric.mod.json').decode('utf-8'))
                    depends = fabric_info.get('depends', {})
                    if 'minecraft' in depends:
                        return depends['minecraft']
                
                elif 'mcmod.info' in zip_file.namelist():
                    mcmod_info = json.loads(zip_file.read('mcmod.info').decode('utf-8'))
                    if isinstance(mcmod_info, list) and len(mcmod_info) > 0:
                        return mcmod_info[0].get('mcversion', 'Unknown')
        except Exception:
            pass
        return "Unknown"
    
    def toggle_mod(self, mod_info: ModInfo):
        try:
            mod_path = Path(mod_info.file_path)
            
            if mod_info.enabled:
                # Move to disabled folder
                new_path = self.vm.disabled_mods_path / mod_path.name
                shutil.move(str(mod_path), str(new_path))
                mod_info.enabled = False
                mod_info.file_path = str(new_path)
            else:
                # Move back to mods folder
                new_path = self.vm.mods_path / mod_path.name
                shutil.move(str(mod_path), str(new_path))
                mod_info.enabled = True
                mod_info.file_path = str(new_path)
                
        except Exception as e:
            logging.error(f"Error toggling mod {mod_info.name}: {e}")
            raise e
    
    def remove_mod(self, mod_info: ModInfo):
        try:
            mod_path = Path(mod_info.file_path)
            if mod_path.exists():
                mod_path.unlink()
        except Exception as e:
            logging.error(f"Error removing mod {mod_info.name}: {e}")
            raise e
    
    def get_resource_packs(self) -> List[Dict]:
        if not self.vm.resource_packs_path.exists():
            return []
        
        packs = []
        try:
            for pack in self.vm.resource_packs_path.iterdir():
                if pack.is_dir() or pack.suffix == ".zip":
                    pack_info = {
                        'name': pack.name,
                        'type': 'folder' if pack.is_dir() else 'zip',
                        'path': str(pack),
                        'size': self.get_folder_size(pack) if pack.is_dir() else pack.stat().st_size,
                        'modified': datetime.fromtimestamp(pack.stat().st_mtime).isoformat()
                    }
                    
                    # Try to get pack description
                    if pack.is_dir():
                        mcmeta_file = pack / "pack.mcmeta"
                        if mcmeta_file.exists():
                            try:
                                with open(mcmeta_file, 'r', encoding='utf-8') as f:
                                    mcmeta = json.load(f)
                                    pack_info['description'] = mcmeta.get('pack', {}).get('description', '')
                            except:
                                pass
                    
                    packs.append(pack_info)
        except Exception as e:
            logging.error(f"Error getting resource packs: {e}")
        
        return packs
    
    def get_folder_size(self, folder_path: Path) -> int:
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(folder_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    total_size += os.path.getsize(filepath)
        except Exception:
            pass
        return total_size
    
    def get_downloaded_modpacks(self) -> List[Dict]:
        """Get modpacks from actual launcher locations"""
        modpacks = []
        home = Path.home()
        
        try:
            # Check CurseForge modpacks
            if platform.system() == "Windows":
                curseforge_paths = [
                    home / "Documents" / "Curseforge" / "Minecraft" / "Instances",
                    home / "curseforge" / "minecraft" / "Instances",
                    Path("C:") / "Users" / "Public" / "Documents" / "Curseforge" / "Minecraft" / "Instances"
                ]
                
                for cf_path in curseforge_paths:
                    if cf_path.exists():
                        logging.info(f"Found CurseForge path: {cf_path}")
                        for instance_dir in cf_path.iterdir():
                            if instance_dir.is_dir():
                                modpacks.append({
                                    'name': instance_dir.name,
                                    'version': 'CurseForge Instance',
                                    'description': f'CurseForge modpack instance from {cf_path.name}',
                                    'file_path': str(instance_dir),
                                    'file_size': self.get_folder_size(instance_dir),
                                    'created_date': datetime.fromtimestamp(instance_dir.stat().st_ctime).isoformat(),
                                    'launcher': 'CurseForge'
                                })
            
            # Check MultiMC instances
            multimc_paths = [
                home / "Documents" / "MultiMC" / "instances",
                home / "MultiMC" / "instances",
                Path("C:") / "MultiMC" / "instances" if platform.system() == "Windows" else None,
                home / ".local" / "share" / "multimc" / "instances"  # Linux
            ]
            
            for mmc_path in multimc_paths:
                if mmc_path and mmc_path.exists():
                    logging.info(f"Found MultiMC path: {mmc_path}")
                    for instance_dir in mmc_path.iterdir():
                        if instance_dir.is_dir():
                            modpacks.append({
                                'name': instance_dir.name,
                                'version': 'MultiMC Instance',
                                'description': f'MultiMC instance from {mmc_path.parent.name}',
                                'file_path': str(instance_dir),
                                'file_size': self.get_folder_size(instance_dir),
                                'created_date': datetime.fromtimestamp(instance_dir.stat().st_ctime).isoformat(),
                                'launcher': 'MultiMC'
                            })
            
            # Check ATLauncher instances
            atlauncher_paths = [
                home / "Documents" / "ATLauncher" / "instances",
                home / "ATLauncher" / "instances",
                home / ".local" / "share" / "ATLauncher" / "instances"  # Linux
            ]
            
            for atl_path in atlauncher_paths:
                if atl_path.exists():
                    logging.info(f"Found ATLauncher path: {atl_path}")
                    for instance_dir in atl_path.iterdir():
                        if instance_dir.is_dir():
                            modpacks.append({
                                'name': instance_dir.name,
                                'version': 'ATLauncher Instance',
                                'description': f'ATLauncher instance from {atl_path.parent.name}',
                                'file_path': str(instance_dir),
                                'file_size': self.get_folder_size(instance_dir),
                                'created_date': datetime.fromtimestamp(instance_dir.stat().st_ctime).isoformat(),
                                'launcher': 'ATLauncher'
                            })
            
            # Check Technic Launcher
            technic_paths = [
                home / "AppData" / "Roaming" / ".technic" / "modpacks" if platform.system() == "Windows" else None,
                home / ".technic" / "modpacks"
            ]
            
            for tech_path in technic_paths:
                if tech_path and tech_path.exists():
                    logging.info(f"Found Technic path: {tech_path}")
                    for pack_dir in tech_path.iterdir():
                        if pack_dir.is_dir():
                            modpacks.append({
                                'name': pack_dir.name,
                                'version': 'Technic Pack',
                                'description': f'Technic Launcher modpack',
                                'file_path': str(pack_dir),
                                'file_size': self.get_folder_size(pack_dir),
                                'created_date': datetime.fromtimestamp(pack_dir.stat().st_ctime).isoformat(),
                                'launcher': 'Technic'
                            })
            
            # Also check our own modpacks folder
            for modpack_file in self.vm.modpacks_path.glob("*.zip"):
                try:
                    with zipfile.ZipFile(modpack_file, 'r') as zf:
                        if 'modpack.json' in zf.namelist():
                            info = json.loads(zf.read('modpack.json').decode('utf-8'))
                            info['file_path'] = str(modpack_file)
                            info['file_size'] = modpack_file.stat().st_size
                            modpacks.append(info)
                except Exception as e:
                    # If we can't read the modpack info, create basic info
                    modpacks.append({
                        'name': modpack_file.stem,
                        'version': 'Custom',
                        'description': 'Custom modpack',
                        'file_path': str(modpack_file),
                        'file_size': modpack_file.stat().st_size,
                        'created_date': datetime.fromtimestamp(modpack_file.stat().st_ctime).isoformat(),
                        'launcher': 'Vanquish Manager'
                    })
                    
        except Exception as e:
            logging.error(f"Error getting downloaded modpacks: {e}")
        
        logging.info(f"Found {len(modpacks)} modpacks total")
        return modpacks

class SkinManager:
    def __init__(self, vanquish_manager: VanquishModManager):
        self.vm = vanquish_manager
    
    def get_minecraft_skins(self) -> List[Dict]:
        """Get skins from actual Minecraft locations and our cache"""
        skins = []
        
        try:
            # Check actual Minecraft skin cache locations
            minecraft_skin_paths = [
                self.vm.minecraft_path / "assets" / "skins",
                self.vm.minecraft_path / "assets" / "minecraft" / "textures" / "entity" / "player",
                Path.home() / ".minecraft" / "assets" / "skins",
                Path.home() / "AppData" / "Roaming" / ".minecraft" / "assets" / "skins" if platform.system() == "Windows" else None
            ]
            
            for skin_path in minecraft_skin_paths:
                if skin_path and skin_path.exists():
                    logging.info(f"Checking skin path: {skin_path}")
                    for skin_file in skin_path.glob("*.png"):
                        skins.append({
                            'username': skin_file.stem,
                            'type': 'minecraft_cache',
                            'file_path': str(skin_file),
                            'file_size': skin_file.stat().st_size,
                            'downloaded_date': datetime.fromtimestamp(skin_file.stat().st_ctime).isoformat()
                        })
            
            # Check launcher profiles for usernames and try to get their skins
            launcher_profiles = self.vm.minecraft_path / "launcher_profiles.json"
            if launcher_profiles.exists():
                try:
                    with open(launcher_profiles, 'r') as f:
                        profiles_data = json.load(f)
                        
                    # Extract usernames from profiles
                    usernames = set()
                    for profile_id, profile_data in profiles_data.get('profiles', {}).items():
                        if 'lastUsedAccount' in profile_data:
                            account_id = profile_data['lastUsedAccount']
                            # Try to get username from account data
                            for auth_data in profiles_data.get('authenticationDatabase', {}).values():
                                if auth_data.get('uuid') == account_id:
                                    username = auth_data.get('displayName', '')
                                    if username:
                                        usernames.add(username)
                    
                    # Download previews for found usernames
                    for username in usernames:
                        self.download_skin_preview(username)
                        
                except Exception as e:
                    logging.error(f"Error reading launcher profiles: {e}")
            
            # Get our downloaded skins
            for skin_file in self.vm.skins_path.glob("*.png"):
                username = skin_file.stem.replace('_preview', '').replace('_full', '')
                skin_type = 'preview' if '_preview' in skin_file.stem else 'full'
                
                skins.append({
                    'username': username,
                    'type': skin_type,
                    'file_path': str(skin_file),
                    'file_size': skin_file.stat().st_size,
                    'downloaded_date': datetime.fromtimestamp(skin_file.stat().st_ctime).isoformat()
                })
                
        except Exception as e:
            logging.error(f"Error getting minecraft skins: {e}")
        
        logging.info(f"Found {len(skins)} skins total")
        return skins
    
    def download_skin_preview(self, username: str) -> Optional[str]:
        try:
            url = f"https://mc-heads.net/avatar/{username}/128"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                skin_file = self.vm.skins_path / f"{username}_preview.png"
                with open(skin_file, 'wb') as f:
                    f.write(response.content)
                logging.info(f"Downloaded skin preview for {username}")
                return str(skin_file)
        except Exception as e:
            logging.error(f"Error downloading skin preview for {username}: {e}")
        return None
    
    def download_full_skin(self, username: str) -> Optional[str]:
        try:
            url = f"https://mc-heads.net/skin/{username}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                skin_file = self.vm.skins_path / f"{username}_full.png"
                with open(skin_file, 'wb') as f:
                    f.write(response.content)
                logging.info(f"Downloaded full skin for {username}")
                return str(skin_file)
        except Exception as e:
            logging.error(f"Error downloading full skin for {username}: {e}")
        return None
    
    def get_downloaded_skins(self) -> List[Dict]:
        return self.get_minecraft_skins()
    
    def get_skinmc_url(self, username: str) -> str:
        return f"https://www.skinmc.net/en/skin/{username}"

class SettingsManager:
    def __init__(self, vanquish_manager: VanquishModManager):
        self.vm = vanquish_manager
        self.settings = self.load_settings()
    
    def load_settings(self) -> Settings:
        try:
            if self.vm.settings_file.exists():
                with open(self.vm.settings_file, 'r') as f:
                    data = json.load(f)
                    # Handle color scheme
                    if 'color_scheme' in data and data['color_scheme']:
                        data['color_scheme'] = ColorScheme(**data['color_scheme'])
                    return Settings(**data)
        except Exception as e:
            logging.error(f"Failed to load settings: {e}")
        
        return Settings()
    
    def save_settings(self):
        try:
            data = asdict(self.settings)
            with open(self.vm.settings_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to save settings: {e}")

class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        self.bind_mousewheel()
    
    def bind_mousewheel(self):
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        def _bind_to_mousewheel(event):
            self.canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        def _unbind_from_mousewheel(event):
            self.canvas.unbind_all("<MouseWheel>")
        
        self.canvas.bind('<Enter>', _bind_to_mousewheel)
        self.canvas.bind('<Leave>', _unbind_from_mousewheel)

class MinecraftModManager:
    def __init__(self):
        self.install_dependencies()
        
        self.root = tk.Tk()
        self.root.title("Minecraft Mod Manager - Made by Vanquish")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 700)
        
        # Initialize managers
        self.minecraft_path = ""
        self.vanquish_manager = None
        self.mod_manager = None
        self.skin_manager = None
        self.settings_manager = None
        self.minecraft_versions = []
        
        self.initialize_minecraft()
        self.setup_logging()
        self.setup_ui()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def install_dependencies(self):
        required_packages = ["requests", "Pillow"]
        for package in required_packages:
            try:
                __import__(package.lower().replace("-", "_"))
            except ImportError:
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                    print(f"Installed {package}")
                except subprocess.CalledProcessError:
                    print(f"Failed to install {package}")
    
    def setup_logging(self):
        # Setup comprehensive logging if debug mode is enabled
        if self.settings_manager and self.settings_manager.settings.debug_mode:
            log_file = self.vanquish_manager.log_file if self.vanquish_manager else "minecraft_mod_manager.log"
            
            # Configure logging with detailed format
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
                handlers=[
                    logging.FileHandler(log_file, mode='a', encoding='utf-8'),
                    logging.StreamHandler(sys.stdout)
                ]
            )
            
            logging.info("="*50)
            logging.info("Minecraft Mod Manager - Debug Session Started")
            logging.info(f"Platform: {platform.system()} {platform.release()}")
            logging.info(f"Python: {sys.version}")
            logging.info("="*50)
        else:
            # Disable logging
            logging.disable(logging.CRITICAL)
    
    def log_action(self, action: str, details: str = ""):
        """Log user actions when debug mode is enabled"""
        if self.settings_manager and self.settings_manager.settings.debug_mode:
            log_message = f"USER ACTION: {action}"
            if details:
                log_message += f" - {details}"
            logging.info(log_message)
    
    def initialize_minecraft(self):
        try:
            # Try to detect Minecraft
            detected_path = MinecraftDetector.detect_minecraft()
            
            if detected_path:
                self.minecraft_path = detected_path
                self.vanquish_manager = VanquishModManager(detected_path)
                self.settings_manager = SettingsManager(self.vanquish_manager)
                
                # Update settings with detected path
                self.settings_manager.settings.minecraft_path = detected_path
                
                # Detect launcher path
                launcher_path = MinecraftDetector.detect_launcher_path()
                if launcher_path:
                    self.settings_manager.settings.launcher_path = launcher_path
                
                self.settings_manager.save_settings()
                
                self.mod_manager = ModManager(self.vanquish_manager)
                self.skin_manager = SkinManager(self.vanquish_manager)
                self.minecraft_versions = MinecraftDetector.get_minecraft_versions(detected_path)
                
                logging.info(f"Minecraft detected at: {detected_path}")
            else:
                # Create temporary settings manager for UI
                temp_path = Path.home() / ".minecraft_temp"
                temp_path.mkdir(exist_ok=True)
                self.vanquish_manager = VanquishModManager(str(temp_path))
                self.settings_manager = SettingsManager(self.vanquish_manager)
                
        except Exception as e:
            logging.error(f"Error initializing Minecraft: {e}")
            messagebox.showerror("Initialization Error", f"Failed to initialize: {e}")
    
    def setup_ui(self):
        self.apply_theme()
        self.create_header()
        self.create_main_layout()
        
        # Show appropriate initial view
        if self.minecraft_path:
            self.show_dashboard()
        else:
            self.show_minecraft_setup()
    
    def apply_theme(self):
        if not self.settings_manager:
            return
            
        self.style_manager = ModernStyle(self.root, self.settings_manager.settings.theme)
    
    def create_header(self):
        if not self.settings_manager:
            return
            
        colors = self.style_manager.colors
        
        # Create gradient header
        header_frame = GradientFrame(self.root, 1400, 80, colors['button_bg'], colors['accent'], 'horizontal')
        header_frame.pack(fill="x", side="top")
        
        # Title and subtitle with better fonts - REMOVED "Professional Edition"
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        title_label = tk.Label(header_frame, text="🎮 Minecraft Mod Manager", 
                              font=(font_family, 24, "bold"), fg="white", bg=colors['button_bg'])
        title_label.place(x=20, y=15)
        
        subtitle_label = tk.Label(header_frame, text="Made by Vanquish", 
                                 font=(font_family, 12), fg="#e2e8f0", bg=colors['button_bg'])
        subtitle_label.place(x=20, y=50)
        
        # Launcher controls - REMOVED theme selector
        if self.minecraft_path:
            launcher_frame = tk.Frame(header_frame, bg=colors['button_bg'])
            launcher_frame.place(x=1000, y=15, width=380, height=50)
            
            ModernButton(launcher_frame, text="🚀 Launch Minecraft", width=120, height=35,
                        command=self.launch_minecraft, bg_color="#10b981", hover_color="#059669").pack(side="left", padx=5)
            
            ModernButton(launcher_frame, text="⚙️ Launch Profile", width=120, height=35,
                        command=self.launch_profile, bg_color="#f59e0b", hover_color="#d97706").pack(side="left", padx=5)
            
            ModernButton(launcher_frame, text="📁 Open .minecraft", width=120, height=35,
                        command=self.open_minecraft_folder, bg_color="#6366f1", hover_color="#4f46e5").pack(side="left", padx=5)
    
    def create_main_layout(self):
        if not self.settings_manager:
            return
            
        colors = self.style_manager.colors
        
        main_container = tk.Frame(self.root, bg=colors['bg'])
        main_container.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Sidebar with modern styling
        sidebar = tk.Frame(main_container, bg=colors['frame_bg'], relief="raised", borderwidth=1)
        sidebar.pack(side="left", fill="y", padx=(0, 15))
        sidebar.pack_propagate(False)
        sidebar.configure(width=300)
        
        # Sidebar header
        sidebar_header = tk.Frame(sidebar, bg=colors['button_bg'], height=60)
        sidebar_header.pack(fill="x")
        sidebar_header.pack_propagate(False)
        
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        nav_title = tk.Label(sidebar_header, text="🧭 Navigation", 
                            font=(font_family, 16, "bold"), fg="white", bg=colors['button_bg'])
        nav_title.pack(pady=15)
        
        # Navigation items
        nav_items = [
            ("🏠 Dashboard", self.show_dashboard),
            ("📦 Installed Mods", self.show_installed_mods),
            ("👥 Mod Profiles", self.show_mod_profiles),
            ("🌟 Popular Mods", self.show_popular_mods),
            ("📋 Modpacks", self.show_modpacks),
            ("📥 Downloaded Modpacks", self.show_downloaded_modpacks),
            ("🎨 Resource Packs", self.show_resource_packs),
            ("👤 Skin Manager", self.show_skin_manager),
            ("🖼️ Downloaded Skins", self.show_downloaded_skins),
            ("🎨 Customize Colors", self.show_color_customizer),
            ("⚙️ Settings", self.show_settings)
        ]
        
        self.nav_buttons = {}
        nav_container = tk.Frame(sidebar, bg=colors['frame_bg'])
        nav_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        for i, (text, command) in enumerate(nav_items):
            # Enhanced button with sharper text
            btn = ModernButton(nav_container, text=text, command=command, 
                             width=270, height=45,
                             bg_color=colors['button_bg'], hover_color=colors['accent'],
                             text_color="white")
            btn.pack(pady=5)
            self.nav_buttons[text] = btn
            
            # Add animation
            if self.settings_manager.settings.animations_enabled:
                animator = AnimatedWidget(btn)
                self.root.after(i * 50, animator.fade_in)
        
        # Main content area
        self.main_frame = tk.Frame(main_container, bg=colors['bg'])
        self.main_frame.pack(side="right", fill="both", expand=True)
        
        self.current_view = None
    
    def clear_main_frame(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()
    
    def show_minecraft_setup(self):
        self.log_action("Show Minecraft Setup")
        self.clear_main_frame()
        
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        setup_frame = tk.Frame(self.main_frame, bg=colors['bg'])
        setup_frame.pack(fill="both", expand=True, padx=50, pady=50)
        
        title_label = tk.Label(setup_frame, text="🚀 Welcome to Minecraft Mod Manager", 
                              font=(font_family, 28, "bold"), fg=colors['fg'], bg=colors['bg'])
        title_label.pack(pady=(0, 30))
        
        info_label = tk.Label(setup_frame, 
                             text="Minecraft installation not detected automatically.\nPlease select your Minecraft directory to continue.",
                             font=(font_family, 16), fg=colors['fg'], bg=colors['bg'], justify="center")
        info_label.pack(pady=(0, 40))
        
        def browse_minecraft():
            self.log_action("Browse Minecraft Directory")
            path = filedialog.askdirectory(title="Select Minecraft Directory")
            if path and Path(path).exists():
                self.log_action("Minecraft Directory Selected", path)
                self.minecraft_path = path
                self.vanquish_manager = VanquishModManager(path)
                self.settings_manager = SettingsManager(self.vanquish_manager)
                self.settings_manager.settings.minecraft_path = path
                
                # Detect launcher
                launcher_path = MinecraftDetector.detect_launcher_path()
                if launcher_path:
                    self.settings_manager.settings.launcher_path = launcher_path
                
                self.settings_manager.save_settings()
                
                self.mod_manager = ModManager(self.vanquish_manager)
                self.skin_manager = SkinManager(self.vanquish_manager)
                self.minecraft_versions = MinecraftDetector.get_minecraft_versions(path)
                
                messagebox.showinfo("Success", "Minecraft directory configured successfully!")
                self.setup_ui()  # Refresh UI
        
        browse_btn = ModernButton(setup_frame, text="📁 Browse for Minecraft Directory", 
                                 command=browse_minecraft, width=350, height=60,
                                 bg_color=colors['button_bg'], hover_color=colors['accent'])
        browse_btn.pack(pady=15)
        
        # Auto-detect button
        def auto_detect():
            self.log_action("Auto-Detect Minecraft")
            detected = MinecraftDetector.detect_minecraft()
            if detected:
                self.log_action("Minecraft Auto-Detected", detected)
                self.minecraft_path = detected
                self.vanquish_manager = VanquishModManager(detected)
                self.settings_manager = SettingsManager(self.vanquish_manager)
                self.settings_manager.settings.minecraft_path = detected
                
                # Detect launcher
                launcher_path = MinecraftDetector.detect_launcher_path()
                if launcher_path:
                    self.settings_manager.settings.launcher_path = launcher_path
                
                self.settings_manager.save_settings()
                
                self.mod_manager = ModManager(self.vanquish_manager)
                self.skin_manager = SkinManager(self.vanquish_manager)
                self.minecraft_versions = MinecraftDetector.get_minecraft_versions(detected)
                
                messagebox.showinfo("Success", f"Minecraft found at: {detected}")
                self.setup_ui()  # Refresh UI
            else:
                self.log_action("Auto-Detect Failed")
                messagebox.showerror("Not Found", "Could not automatically detect Minecraft installation.")
        
        auto_btn = ModernButton(setup_frame, text="🔍 Try Auto-Detect Again", 
                               command=auto_detect, width=350, height=60,
                               bg_color="#10b981", hover_color="#059669")
        auto_btn.pack(pady=15)
    
    def show_dashboard(self):
        self.log_action("Show Dashboard")
        if not self.mod_manager:
            self.show_minecraft_setup()
            return
            
        self.clear_main_frame()
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        # Create scrollable dashboard
        dashboard_scroll = ScrollableFrame(self.main_frame)
        dashboard_scroll.pack(fill="both", expand=True)
        
        dashboard = dashboard_scroll.scrollable_frame
        dashboard.configure(style='TFrame')
        
        # Welcome section with modern styling
        welcome_frame = GradientFrame(dashboard, 800, 100, colors['button_bg'], colors['accent'], 'horizontal')
        welcome_frame.pack(fill="x", pady=(0, 20), padx=20)
        
        welcome_label = tk.Label(welcome_frame, text="🎮 Welcome to Your Mod Manager Dashboard", 
                                font=(font_family, 22, "bold"), fg="white", bg=colors['button_bg'])
        welcome_label.place(x=30, y=30)
        
        # Stats cards with modern design
        stats_frame = tk.Frame(dashboard, bg=colors['bg'])
        stats_frame.pack(fill="x", pady=(0, 20), padx=20)
        
        # Get statistics
        mods = self.mod_manager.get_installed_mods()
        enabled_mods = len([m for m in mods if m.enabled])
        total_mods = len(mods)
        
        profiles = self.mod_manager.profile_manager.get_profiles()
        resource_packs = self.mod_manager.get_resource_packs()
        downloaded_modpacks = self.mod_manager.get_downloaded_modpacks()
        downloaded_skins = self.skin_manager.get_downloaded_skins()
        
        stats = [
            ("📦 Total Mods", str(total_mods), colors['button_bg']),
            ("✅ Enabled Mods", str(enabled_mods), "#10b981"),
            ("👥 Profiles", str(len(profiles)), colors['accent']),
            ("🎨 Resource Packs", str(len(resource_packs)), "#f59e0b"),
            ("📋 Downloaded Modpacks", str(len(downloaded_modpacks)), "#8b5cf6"),
            ("👤 Downloaded Skins", str(len(downloaded_skins)), "#ef4444")
        ]
        
        for i, (label, value, color) in enumerate(stats):
            card = GradientFrame(stats_frame, 200, 120, color, self.lighten_color(color, 1.2), 'vertical')
            card.grid(row=i//3, column=i%3, padx=15, pady=15, sticky="ew")
            
            value_label = tk.Label(card, text=value, font=(font_family, 28, "bold"), 
                                  fg="white", bg=color)
            value_label.place(x=100, y=25, anchor="center")
            
            label_label = tk.Label(card, text=label, font=(font_family, 12, "bold"), 
                                  fg="white", bg=color)
            label_label.place(x=100, y=80, anchor="center")
        
        # Configure grid weights
        for i in range(3):
            stats_frame.columnconfigure(i, weight=1)
        
        # Quick actions with modern styling
        actions_frame = tk.Frame(dashboard, bg=colors['frame_bg'], relief="raised", borderwidth=1)
        actions_frame.pack(fill="x", pady=20, padx=20)
        
        actions_header = tk.Frame(actions_frame, bg=colors['button_bg'], height=50)
        actions_header.pack(fill="x")
        actions_header.pack_propagate(False)
        
        actions_title = tk.Label(actions_header, text="🚀 Quick Actions", 
                               font=(font_family, 16, "bold"), fg="white", bg=colors['button_bg'])
        actions_title.pack(pady=12)
        
        actions = [
            ("➕ Add New Mod", self.add_mod, colors['button_bg']),
            ("👥 Switch Profile", self.show_mod_profiles, colors['accent']),
            ("🌟 Browse Popular Mods", self.show_popular_mods, "#10b981"),
            ("📋 Create Modpack", self.create_modpack, "#f59e0b"),
            ("👤 Download Skin", self.show_skin_manager, "#ef4444"),
            ("⚙️ Open Settings", self.show_settings, "#8b5cf6")
        ]
        
        actions_grid = tk.Frame(actions_frame, bg=colors['frame_bg'])
        actions_grid.pack(fill="x", padx=20, pady=20)
        
        for i, (text, command, color) in enumerate(actions):
            btn = ModernButton(actions_grid, text=text, command=command, 
                             width=220, height=50, bg_color=color, hover_color=self.lighten_color(color, 1.1))
            btn.grid(row=i//3, column=i%3, padx=10, pady=10)
        
        # Configure grid weights
        for i in range(3):
            actions_grid.columnconfigure(i, weight=1)
        
        # System information
        info_frame = tk.Frame(dashboard, bg=colors['frame_bg'], relief="raised", borderwidth=1)
        info_frame.pack(fill="x", pady=20, padx=20)
        
        info_header = tk.Frame(info_frame, bg=colors['button_bg'], height=50)
        info_header.pack(fill="x")
        info_header.pack_propagate(False)
        
        info_title = tk.Label(info_header, text="📊 System Information", 
                            font=(font_family, 16, "bold"), fg="white", bg=colors['button_bg'])
        info_title.pack(pady=12)
        
        info_text = f"""
🏠 Minecraft Path: {self.minecraft_path}
📁 Manager Data: {self.vanquish_manager.manager_path}
🎮 Minecraft Versions: {len(self.minecraft_versions)} detected
🔧 Mod Loaders: {', '.join(self.get_detected_loaders())}
💾 Current Profile: {self.settings_manager.settings.current_profile}
🎨 Theme: {self.settings_manager.settings.theme.title()}
🚀 Launcher: {'Detected' if self.settings_manager.settings.launcher_path else 'Not Found'}
🐛 Debug Mode: {'Enabled' if self.settings_manager.settings.debug_mode else 'Disabled'}
        """.strip()
        
        info_label = tk.Label(info_frame, text=info_text, font=(font_family, 11), 
                             fg=colors['fg'], bg=colors['frame_bg'], justify="left")
        info_label.pack(anchor="w", padx=20, pady=20)
    
    def lighten_color(self, color, factor):
        try:
            color = color.lstrip('#')
            rgb = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
            rgb = tuple(min(255, int(c * factor)) for c in rgb)
            return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        except:
            return color
    
    def get_detected_loaders(self) -> List[str]:
        if not self.minecraft_path:
            return []
        
        loaders = MinecraftDetector.detect_mod_loaders(self.minecraft_path)
        detected = []
        for loader, versions in loaders.items():
            if versions:
                detected.append(f"{loader.title()} ({len(versions)})")
        
        return detected if detected else ["None"]
    
    def show_installed_mods(self):
        self.log_action("Show Installed Mods")
        if not self.mod_manager:
            self.show_minecraft_setup()
            return
            
        self.current_view = 'installed_mods'
        self.clear_main_frame()
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        # Header
        header_frame = GradientFrame(self.main_frame, 800, 80, colors['button_bg'], colors['accent'], 'horizontal')
        header_frame.pack(fill="x", pady=(0, 20))
        
        title_label = tk.Label(header_frame, text="📦 Installed Mods", 
                              font=(font_family, 20, "bold"), fg="white", bg=colors['button_bg'])
        title_label.place(x=30, y=25)
        
        # Action buttons
        button_frame = tk.Frame(self.main_frame, bg=colors['bg'])
        button_frame.pack(fill="x", pady=(0, 20), padx=20)
        
        ModernButton(button_frame, text="➕ Add Mod", command=self.add_mod,
                    width=120, height=40, bg_color="#10b981", hover_color="#059669").pack(side="left", padx=10)
        ModernButton(button_frame, text="🔄 Refresh", command=self.show_installed_mods,
                    width=120, height=40, bg_color=colors['accent'], hover_color=colors['button_bg']).pack(side="left", padx=10)
        ModernButton(button_frame, text="📁 Open Mods Folder", command=self.open_mods_folder,
                    width=160, height=40, bg_color="#f59e0b", hover_color="#d97706").pack(side="left", padx=10)
        
        # Mods list
        scrollable_frame = ScrollableFrame(self.main_frame)
        scrollable_frame.pack(fill="both", expand=True, padx=20)
        
        try:
            mods = self.mod_manager.get_installed_mods()
            
            if not mods:
                no_mods_frame = tk.Frame(scrollable_frame.scrollable_frame, bg=colors['frame_bg'], 
                                       relief="raised", borderwidth=2)
                no_mods_frame.pack(fill="x", pady=20, padx=20)
                
                no_mods_label = tk.Label(no_mods_frame, 
                                       text="📦 No mods installed.\nClick 'Add Mod' to get started!", 
                                       font=(font_family, 16), fg=colors['fg'], bg=colors['frame_bg'], justify="center")
                no_mods_label.pack(pady=40)
                return
            
            for mod in mods:
                self.create_mod_item(scrollable_frame.scrollable_frame, mod)
                
        except Exception as e:
            logging.error(f"Error displaying mods: {e}")
            error_label = tk.Label(scrollable_frame.scrollable_frame, 
                                 text=f"❌ Error loading mods: {e}", 
                                 fg="#ef4444", bg=colors['bg'])
            error_label.pack(pady=20)
    
    def create_mod_item(self, parent, mod: ModInfo):
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        mod_frame = tk.Frame(parent, bg=colors['frame_bg'], relief="raised", borderwidth=1)
        mod_frame.pack(fill="x", pady=5, padx=10)
        
        # Mod info section
        info_frame = tk.Frame(mod_frame, bg=colors['frame_bg'])
        info_frame.pack(side="left", fill="both", expand=True, padx=20, pady=15)
        
        # Status icon and name
        status_icon = "✅" if mod.enabled else "❌"
        name_label = tk.Label(info_frame, text=f"{status_icon} {mod.name}", 
                             font=(font_family, 14, "bold"), fg=colors['fg'], bg=colors['frame_bg'])
        name_label.pack(anchor="w")
        
        # Description if available
        if mod.description:
            desc_label = tk.Label(info_frame, text=mod.description, 
                                font=(font_family, 10), fg=colors['accent'], bg=colors['frame_bg'])
            desc_label.pack(anchor="w")
        
        # Mod details
        details_text = f"🔧 {mod.loader} | 📋 v{mod.version} | 🎮 MC {mod.minecraft_version}"
        details_label = tk.Label(info_frame, text=details_text, 
                               font=(font_family, 9), fg=colors['fg'], bg=colors['frame_bg'])
        details_label.pack(anchor="w")
        
        # Buttons section
        button_frame = tk.Frame(mod_frame, bg=colors['frame_bg'])
        button_frame.pack(side="right", padx=20, pady=15)
        
        toggle_text = "Disable" if mod.enabled else "Enable"
        toggle_color = "#ef4444" if mod.enabled else "#10b981"
        ModernButton(button_frame, text=toggle_text, width=80, height=35,
                    command=lambda: self.toggle_mod(mod), 
                    bg_color=toggle_color, hover_color=self.lighten_color(toggle_color, 1.1)).pack(side="left", padx=5)
        
        ModernButton(button_frame, text="🗑️ Remove", width=80, height=35,
                    command=lambda: self.remove_mod(mod), 
                    bg_color="#ef4444", hover_color="#dc2626").pack(side="left", padx=5)
    
    def show_mod_profiles(self):
        self.log_action("Show Mod Profiles")
        if not self.mod_manager:
            self.show_minecraft_setup()
            return
            
        self.clear_main_frame()
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        # Header
        header_frame = GradientFrame(self.main_frame, 800, 80, colors['button_bg'], colors['accent'], 'horizontal')
        header_frame.pack(fill="x", pady=(0, 20))
        
        title_label = tk.Label(header_frame, text="👥 Mod Profiles", 
                              font=(font_family, 20, "bold"), fg="white", bg=colors['button_bg'])
        title_label.place(x=30, y=25)
        
        # Action buttons
        button_frame = tk.Frame(self.main_frame, bg=colors['bg'])
        button_frame.pack(fill="x", pady=(0, 20), padx=20)
        
        ModernButton(button_frame, text="➕ Create Profile", command=self.create_profile,
                    width=140, height=40, bg_color="#10b981", hover_color="#059669").pack(side="left", padx=10)
        ModernButton(button_frame, text="🔄 Refresh", command=self.show_mod_profiles,
                    width=120, height=40, bg_color=colors['accent'], hover_color=colors['button_bg']).pack(side="left", padx=10)
        
        # Profiles list
        scrollable_frame = ScrollableFrame(self.main_frame)
        scrollable_frame.pack(fill="both", expand=True, padx=20)
        
        try:
            profiles = self.mod_manager.profile_manager.get_profiles()
            
            for profile in profiles:
                self.create_profile_item(scrollable_frame.scrollable_frame, profile)
                
        except Exception as e:
            logging.error(f"Error displaying profiles: {e}")
            error_label = tk.Label(scrollable_frame.scrollable_frame, 
                                 text=f"❌ Error loading profiles: {e}", 
                                 fg="#ef4444", bg=colors['bg'])
            error_label.pack(pady=20)
    
    def create_profile_item(self, parent, profile: ModProfile):
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        profile_frame = tk.Frame(parent, bg=colors['frame_bg'], relief="raised", borderwidth=1)
        profile_frame.pack(fill="x", pady=5, padx=10)
        
        # Profile info section
        info_frame = tk.Frame(profile_frame, bg=colors['frame_bg'])
        info_frame.pack(side="left", fill="both", expand=True, padx=20, pady=15)
        
        # Profile name
        is_current = profile.name.lower() == self.settings_manager.settings.current_profile.lower()
        current_icon = "⭐" if is_current else ""
        name_label = tk.Label(info_frame, text=f"{current_icon} {profile.name}", 
                             font=(font_family, 14, "bold"), fg=colors['fg'], bg=colors['frame_bg'])
        name_label.pack(anchor="w")
        
        # Description
        desc_label = tk.Label(info_frame, text=profile.description, 
                            font=(font_family, 10), fg=colors['accent'], bg=colors['frame_bg'])
        desc_label.pack(anchor="w")
        
        # Profile details
        details_text = f"🎮 MC {profile.minecraft_version} | 🔧 {profile.mod_loader} | 📦 {len(profile.mods)} mods"
        details_label = tk.Label(info_frame, text=details_text, 
                               font=(font_family, 9), fg=colors['fg'], bg=colors['frame_bg'])
        details_label.pack(anchor="w")
        
        # Buttons section
        button_frame = tk.Frame(profile_frame, bg=colors['frame_bg'])
        button_frame.pack(side="right", padx=20, pady=15)
        
        if not is_current:
            ModernButton(button_frame, text="🔄 Switch", width=80, height=35,
                        command=lambda: self.switch_profile(profile), 
                        bg_color="#10b981", hover_color="#059669").pack(side="left", padx=5)
        
        ModernButton(button_frame, text="✏️ Edit", width=80, height=35,
                    command=lambda: self.edit_profile(profile), 
                    bg_color=colors['accent'], hover_color=colors['button_bg']).pack(side="left", padx=5)
        
        if profile.name.lower() != "default":
            ModernButton(button_frame, text="🗑️ Delete", width=80, height=35,
                        command=lambda: self.delete_profile(profile), 
                        bg_color="#ef4444", hover_color="#dc2626").pack(side="left", padx=5)
    
    def show_popular_mods(self):
        self.log_action("Show Popular Mods")
        if not self.mod_manager:
            self.show_minecraft_setup()
            return
            
        self.clear_main_frame()
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        # Header
        header_frame = GradientFrame(self.main_frame, 800, 80, colors['button_bg'], colors['accent'], 'horizontal')
        header_frame.pack(fill="x", pady=(0, 20))
        
        title_label = tk.Label(header_frame, text="🌟 Popular Mods", 
                              font=(font_family, 20, "bold"), fg="white", bg=colors['button_bg'])
        title_label.place(x=30, y=25)
        
        # Search and filter
        search_frame = tk.Frame(self.main_frame, bg=colors['frame_bg'], relief="raised", borderwidth=1)
        search_frame.pack(fill="x", pady=(0, 20), padx=20)
        
        search_container = tk.Frame(search_frame, bg=colors['frame_bg'])
        search_container.pack(fill="x", padx=20, pady=15)
        
        tk.Label(search_container, text="🔍 Search:", font=(font_family, 12, "bold"),
                fg=colors['fg'], bg=colors['frame_bg']).pack(side="left", padx=(0, 10))
        
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_container, textvariable=self.search_var, width=30, font=(font_family, 11))
        search_entry.pack(side="left", padx=(0, 20))
        search_entry.bind("<KeyRelease>", self.filter_popular_mods)
        
        tk.Label(search_container, text="Category:", font=(font_family, 12, "bold"),
                fg=colors['fg'], bg=colors['frame_bg']).pack(side="left", padx=(0, 10))
        
        categories = ["All"] + sorted(list(set(mod["category"] for mod in PopularModsData.POPULAR_MODS)))
        self.category_var = tk.StringVar(value="All")
        category_combo = ttk.Combobox(search_container, textvariable=self.category_var, 
                                    values=categories, state="readonly", width=15, font=(font_family, 11))
        category_combo.pack(side="left")
        category_combo.bind("<<ComboboxSelected>>", self.filter_popular_mods)
        
        info_label = tk.Label(self.main_frame, 
                             text="💡 Click 'CurseForge' or 'Modrinth' to visit mod pages", 
                             font=(font_family, 11, "italic"), fg=colors['accent'], bg=colors['bg'])
        info_label.pack(pady=(0, 15))
        
        self.popular_mods_frame = ScrollableFrame(self.main_frame)
        self.popular_mods_frame.pack(fill="both", expand=True, padx=20)
        
        self.display_popular_mods(PopularModsData.POPULAR_MODS)
    
    def filter_popular_mods(self, event=None):
        search_term = self.search_var.get().lower()
        category = self.category_var.get()
        
        filtered_mods = []
        for mod in PopularModsData.POPULAR_MODS:
            if search_term in mod["name"].lower():
                if category == "All" or mod["category"] == category:
                    filtered_mods.append(mod)
        
        self.display_popular_mods(filtered_mods)
    
    def display_popular_mods(self, mods):
        for widget in self.popular_mods_frame.scrollable_frame.winfo_children():
            widget.destroy()
        
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        for mod in mods:
            mod_frame = tk.Frame(self.popular_mods_frame.scrollable_frame, bg=colors['frame_bg'], 
                               relief="raised", borderwidth=1)
            mod_frame.pack(fill="x", pady=5, padx=10)
            
            info_frame = tk.Frame(mod_frame, bg=colors['frame_bg'])
            info_frame.pack(side="left", fill="both", expand=True, padx=20, pady=15)
            
            name_label = tk.Label(info_frame, text=mod["name"], 
                                font=(font_family, 14, "bold"), fg=colors['fg'], bg=colors['frame_bg'])
            name_label.pack(anchor="w")
            
            desc_label = tk.Label(info_frame, text=mod.get("description", ""), 
                                font=(font_family, 10), fg=colors['accent'], bg=colors['frame_bg'])
            desc_label.pack(anchor="w")
            
            details_text = f"🔧 {mod['loader']} | 📂 {mod['category']}"
            details_label = tk.Label(info_frame, text=details_text, 
                                   font=(font_family, 9), fg=colors['fg'], bg=colors['frame_bg'])
            details_label.pack(anchor="w")
            
            button_frame = tk.Frame(mod_frame, bg=colors['frame_bg'])
            button_frame.pack(side="right", padx=20, pady=15)
            
            ModernButton(button_frame, text="📥 CurseForge", width=120, height=35,
                        command=lambda: webbrowser.open("https://www.curseforge.com/minecraft/mc-mods"),
                        bg_color="#f16436", hover_color="#e55527").pack(side="left", padx=5)
            
            ModernButton(button_frame, text="📥 Modrinth", width=120, height=35,
                        command=lambda: webbrowser.open("https://modrinth.com/mods"),
                        bg_color="#1bd96a", hover_color="#17c65d").pack(side="left", padx=5)
    
    def show_modpacks(self):
        self.log_action("Show Modpacks")
        if not self.mod_manager:
            self.show_minecraft_setup()
            return
            
        self.clear_main_frame()
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        # Header
        header_frame = GradientFrame(self.main_frame, 800, 80, colors['button_bg'], colors['accent'], 'horizontal')
        header_frame.pack(fill="x", pady=(0, 20))
        
        title_label = tk.Label(header_frame, text="📋 Popular Modpacks", 
                              font=(font_family, 20, "bold"), fg="white", bg=colors['button_bg'])
        title_label.place(x=30, y=25)
        
        # Search and filter
        search_frame = tk.Frame(self.main_frame, bg=colors['frame_bg'], relief="raised", borderwidth=1)
        search_frame.pack(fill="x", pady=(0, 20), padx=20)
        
        search_container = tk.Frame(search_frame, bg=colors['frame_bg'])
        search_container.pack(fill="x", padx=20, pady=15)
        
        tk.Label(search_container, text="🔍 Search:", font=(font_family, 12, "bold"),
                fg=colors['fg'], bg=colors['frame_bg']).pack(side="left", padx=(0, 10))
        
        self.modpack_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_container, textvariable=self.modpack_search_var, width=30, font=(font_family, 11))
        search_entry.pack(side="left", padx=(0, 20))
        search_entry.bind("<KeyRelease>", self.filter_modpacks)
        
        tk.Label(search_container, text="Category:", font=(font_family, 12, "bold"),
                fg=colors['fg'], bg=colors['frame_bg']).pack(side="left", padx=(0, 10))
        
        categories = ["All"] + sorted(list(set(pack["category"] for pack in PopularModsData.POPULAR_MODPACKS)))
        self.modpack_category_var = tk.StringVar(value="All")
        category_combo = ttk.Combobox(search_container, textvariable=self.modpack_category_var, 
                                    values=categories, state="readonly", width=15, font=(font_family, 11))
        category_combo.pack(side="left")
        category_combo.bind("<<ComboboxSelected>>", self.filter_modpacks)
        
        info_label = tk.Label(self.main_frame, 
                             text="💡 Click 'Download' to visit CurseForge modpack pages", 
                             font=(font_family, 11, "italic"), fg=colors['accent'], bg=colors['bg'])
        info_label.pack(pady=(0, 15))
        
        self.modpacks_frame = ScrollableFrame(self.main_frame)
        self.modpacks_frame.pack(fill="both", expand=True, padx=20)
        
        self.display_modpacks(PopularModsData.POPULAR_MODPACKS)
    
    def filter_modpacks(self, event=None):
        search_term = self.modpack_search_var.get().lower()
        category = self.modpack_category_var.get()
        
        filtered_packs = []
        for pack in PopularModsData.POPULAR_MODPACKS:
            if search_term in pack["name"].lower():
                if category == "All" or pack["category"] == category:
                    filtered_packs.append(pack)
        
        self.display_modpacks(filtered_packs)
    
    def display_modpacks(self, modpacks):
        for widget in self.modpacks_frame.scrollable_frame.winfo_children():
            widget.destroy()
        
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        for pack in modpacks:
            pack_frame = tk.Frame(self.modpacks_frame.scrollable_frame, bg=colors['frame_bg'], 
                                relief="raised", borderwidth=1)
            pack_frame.pack(fill="x", pady=5, padx=10)
            
            info_frame = tk.Frame(pack_frame, bg=colors['frame_bg'])
            info_frame.pack(side="left", fill="both", expand=True, padx=20, pady=15)
            
            name_label = tk.Label(info_frame, text=pack["name"], 
                                font=(font_family, 14, "bold"), fg=colors['fg'], bg=colors['frame_bg'])
            name_label.pack(anchor="w")
            
            desc_label = tk.Label(info_frame, text=pack.get("description", ""), 
                                font=(font_family, 10), fg=colors['accent'], bg=colors['frame_bg'])
            desc_label.pack(anchor="w")
            
            category_label = tk.Label(info_frame, text=f"📂 Category: {pack['category']}", 
                                    font=(font_family, 9), fg=colors['fg'], bg=colors['frame_bg'])
            category_label.pack(anchor="w")
            
            button_frame = tk.Frame(pack_frame, bg=colors['frame_bg'])
            button_frame.pack(side="right", padx=20, pady=15)
            
            ModernButton(button_frame, text="📥 Download", width=120, height=35,
                        command=lambda: webbrowser.open("https://www.curseforge.com/minecraft/modpacks"),
                        bg_color="#f16436", hover_color="#e55527").pack()
    
    def show_downloaded_modpacks(self):
        self.log_action("Show Downloaded Modpacks")
        if not self.mod_manager:
            self.show_minecraft_setup()
            return
            
        self.clear_main_frame()
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        # Header
        header_frame = GradientFrame(self.main_frame, 800, 80, colors['button_bg'], colors['accent'], 'horizontal')
        header_frame.pack(fill="x", pady=(0, 20))
        
        title_label = tk.Label(header_frame, text="📥 Downloaded Modpacks", 
                              font=(font_family, 20, "bold"), fg="white", bg=colors['button_bg'])
        title_label.place(x=30, y=25)
        
        # Action buttons
        button_frame = tk.Frame(self.main_frame, bg=colors['bg'])
        button_frame.pack(fill="x", pady=(0, 20), padx=20)
        
        ModernButton(button_frame, text="🔄 Refresh", command=self.show_downloaded_modpacks,
                    width=120, height=40, bg_color=colors['accent'], hover_color=colors['button_bg']).pack(side="left", padx=10)
        ModernButton(button_frame, text="📁 Open Folder", command=self.open_modpacks_folder,
                    width=140, height=40, bg_color="#f59e0b", hover_color="#d97706").pack(side="left", padx=10)
        
        # Modpacks list
        scrollable_frame = ScrollableFrame(self.main_frame)
        scrollable_frame.pack(fill="both", expand=True, padx=20)
        
        try:
            modpacks = self.mod_manager.get_downloaded_modpacks()
            
            if not modpacks:
                no_packs_frame = tk.Frame(scrollable_frame.scrollable_frame, bg=colors['frame_bg'], 
                                        relief="raised", borderwidth=2)
                no_packs_frame.pack(fill="x", pady=20, padx=20)
                
                no_packs_label = tk.Label(no_packs_frame, 
                                        text="📋 No modpacks found.\nDownload some modpacks to see them here!", 
                                        font=(font_family, 16), fg=colors['fg'], bg=colors['frame_bg'], justify="center")
                no_packs_label.pack(pady=40)
                return
            
            for modpack in modpacks:
                self.create_modpack_item(scrollable_frame.scrollable_frame, modpack)
                
        except Exception as e:
            logging.error(f"Error displaying modpacks: {e}")
            error_label = tk.Label(scrollable_frame.scrollable_frame, 
                                 text=f"❌ Error loading modpacks: {e}", 
                                 fg="#ef4444", bg=colors['bg'])
            error_label.pack(pady=20)
    
    def create_modpack_item(self, parent, modpack: Dict):
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        pack_frame = tk.Frame(parent, bg=colors['frame_bg'], relief="raised", borderwidth=1)
        pack_frame.pack(fill="x", pady=5, padx=10)
        
        # Pack info section
        info_frame = tk.Frame(pack_frame, bg=colors['frame_bg'])
        info_frame.pack(side="left", fill="both", expand=True, padx=20, pady=15)
        
        # Pack name and launcher
        launcher_icon = "🔧" if modpack.get('launcher') else "📦"
        name_label = tk.Label(info_frame, text=f"{launcher_icon} {modpack['name']}", 
                             font=(font_family, 14, "bold"), fg=colors['fg'], bg=colors['frame_bg'])
        name_label.pack(anchor="w")
        
        # Description
        desc_label = tk.Label(info_frame, text=modpack.get('description', ''), 
                            font=(font_family, 10), fg=colors['accent'], bg=colors['frame_bg'])
        desc_label.pack(anchor="w")
        
        # Pack details
        size_mb = modpack.get('file_size', 0) / (1024 * 1024) if modpack.get('file_size', 0) > 0 else 0
        details_text = f"📋 v{modpack.get('version', 'Unknown')} | 💾 {size_mb:.1f} MB"
        if modpack.get('launcher'):
            details_text += f" | 🚀 {modpack['launcher']}"
        details_label = tk.Label(info_frame, text=details_text, 
                               font=(font_family, 9), fg=colors['fg'], bg=colors['frame_bg'])
        details_label.pack(anchor="w")
        
        # Buttons section
        button_frame = tk.Frame(pack_frame, bg=colors['frame_bg'])
        button_frame.pack(side="right", padx=20, pady=15)
        
        ModernButton(button_frame, text="📁 Open", width=80, height=35,
                    command=lambda: self.open_modpack(modpack['file_path']), 
                    bg_color=colors['accent'], hover_color=colors['button_bg']).pack(side="left", padx=5)
        
        if not modpack.get('launcher'):  # Only show remove for our own modpacks
            ModernButton(button_frame, text="🗑️ Remove", width=80, height=35,
                        command=lambda: self.remove_modpack(modpack['name']), 
                        bg_color="#ef4444", hover_color="#dc2626").pack(side="left", padx=5)
    
    def show_resource_packs(self):
        self.log_action("Show Resource Packs")
        if not self.mod_manager:
            self.show_minecraft_setup()
            return
            
        self.clear_main_frame()
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        # Header
        header_frame = GradientFrame(self.main_frame, 800, 80, colors['button_bg'], colors['accent'], 'horizontal')
        header_frame.pack(fill="x", pady=(0, 20))
        
        title_label = tk.Label(header_frame, text="🎨 Resource Packs", 
                              font=(font_family, 20, "bold"), fg="white", bg=colors['button_bg'])
        title_label.place(x=30, y=25)
        
        # Action buttons
        button_frame = tk.Frame(self.main_frame, bg=colors['bg'])
        button_frame.pack(fill="x", pady=(0, 20), padx=20)
        
        ModernButton(button_frame, text="➕ Add Resource Pack", command=self.add_resource_pack,
                    width=180, height=40, bg_color="#10b981", hover_color="#059669").pack(side="left", padx=10)
        ModernButton(button_frame, text="🔄 Refresh", command=self.show_resource_packs,
                    width=120, height=40, bg_color=colors['accent'], hover_color=colors['button_bg']).pack(side="left", padx=10)
        ModernButton(button_frame, text="📁 Open Folder", command=self.open_resource_packs_folder,
                    width=140, height=40, bg_color="#f59e0b", hover_color="#d97706").pack(side="left", padx=10)
        
        # Resource packs list
        scrollable_frame = ScrollableFrame(self.main_frame)
        scrollable_frame.pack(fill="both", expand=True, padx=20)
        
        try:
            packs = self.mod_manager.get_resource_packs()
            
            if not packs:
                no_packs_frame = tk.Frame(scrollable_frame.scrollable_frame, bg=colors['frame_bg'], 
                                        relief="raised", borderwidth=2)
                no_packs_frame.pack(fill="x", pady=20, padx=20)
                
                no_packs_label = tk.Label(no_packs_frame, 
                                        text="🎨 No resource packs installed.\nClick 'Add Resource Pack' to get started!", 
                                        font=(font_family, 16), fg=colors['fg'], bg=colors['frame_bg'], justify="center")
                no_packs_label.pack(pady=40)
                return
            
            for pack in packs:
                self.create_resource_pack_item(scrollable_frame.scrollable_frame, pack)
                
        except Exception as e:
            logging.error(f"Error displaying resource packs: {e}")
            error_label = tk.Label(scrollable_frame.scrollable_frame, 
                                 text=f"❌ Error loading resource packs: {e}", 
                                 fg="#ef4444", bg=colors['bg'])
            error_label.pack(pady=20)
    
    def create_resource_pack_item(self, parent, pack: Dict):
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        pack_frame = tk.Frame(parent, bg=colors['frame_bg'], relief="raised", borderwidth=1)
        pack_frame.pack(fill="x", pady=5, padx=10)
        
        # Pack info section
        info_frame = tk.Frame(pack_frame, bg=colors['frame_bg'])
        info_frame.pack(side="left", fill="both", expand=True, padx=20, pady=15)
        
        # Pack name and type
        type_icon = "📁" if pack['type'] == 'folder' else "📦"
        name_label = tk.Label(info_frame, text=f"{type_icon} {pack['name']}", 
                             font=(font_family, 14, "bold"), fg=colors['fg'], bg=colors['frame_bg'])
        name_label.pack(anchor="w")
        
        # Description if available
        if pack.get('description'):
            desc_label = tk.Label(info_frame, text=pack['description'], 
                                font=(font_family, 10), fg=colors['accent'], bg=colors['frame_bg'])
            desc_label.pack(anchor="w")
        
        # File info
        size_mb = pack['size'] / (1024 * 1024) if pack['size'] > 0 else 0
        details_text = f"💾 {size_mb:.1f} MB | 📅 Modified: {pack['modified'][:10]}"
        details_label = tk.Label(info_frame, text=details_text, 
                               font=(font_family, 9), fg=colors['fg'], bg=colors['frame_bg'])
        details_label.pack(anchor="w")
        
        # Buttons section
        button_frame = tk.Frame(pack_frame, bg=colors['frame_bg'])
        button_frame.pack(side="right", padx=20, pady=15)
        
        ModernButton(button_frame, text="📁 Open", width=80, height=35,
                    command=lambda: self.open_resource_pack(pack['path']), 
                    bg_color=colors['accent'], hover_color=colors['button_bg']).pack(side="left", padx=5)
        
        ModernButton(button_frame, text="🗑️ Remove", width=80, height=35,
                    command=lambda: self.remove_resource_pack(pack['name']), 
                    bg_color="#ef4444", hover_color="#dc2626").pack(side="left", padx=5)
    
    def show_skin_manager(self):
        self.log_action("Show Skin Manager")
        if not self.skin_manager:
            self.show_minecraft_setup()
            return
            
        self.clear_main_frame()
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        # Header
        header_frame = GradientFrame(self.main_frame, 800, 80, colors['button_bg'], colors['accent'], 'horizontal')
        header_frame.pack(fill="x", pady=(0, 20))
        
        title_label = tk.Label(header_frame, text="👤 Skin Manager", 
                              font=(font_family, 20, "bold"), fg="white", bg=colors['button_bg'])
        title_label.place(x=30, y=25)
        
        # Skin download section
        input_frame = tk.Frame(self.main_frame, bg=colors['frame_bg'], relief="raised", borderwidth=1)
        input_frame.pack(fill="x", pady=(0, 20), padx=20)
        
        input_header = tk.Frame(input_frame, bg=colors['button_bg'], height=50)
        input_header.pack(fill="x")
        input_header.pack_propagate(False)
        
        input_title = tk.Label(input_header, text="🔍 Download Skin Preview", 
                             font=(font_family, 14, "bold"), fg="white", bg=colors['button_bg'])
        input_title.pack(pady=12)
        
        username_frame = tk.Frame(input_frame, bg=colors['frame_bg'])
        username_frame.pack(fill="x", padx=20, pady=20)
        
        tk.Label(username_frame, text="Username:", font=(font_family, 12, "bold"),
                fg=colors['fg'], bg=colors['frame_bg']).pack(side="left", padx=(0, 10))
        
        self.username_var = tk.StringVar(value=self.settings_manager.settings.skin_username)
        username_entry = ttk.Entry(username_frame, textvariable=self.username_var, width=25, font=(font_family, 11))
        username_entry.pack(side="left", padx=(0, 15))
        
        ModernButton(username_frame, text="🔍 Preview", command=self.preview_skin,
                    width=100, height=35, bg_color="#10b981", hover_color="#059669").pack(side="left", padx=5)
        ModernButton(username_frame, text="📥 Download Full", command=self.download_full_skin,
                    width=130, height=35, bg_color=colors['accent'], hover_color=colors['button_bg']).pack(side="left", padx=5)
        ModernButton(username_frame, text="🌐 Visit SkinMC", command=self.open_skinmc,
                    width=130, height=35, bg_color="#f59e0b", hover_color="#d97706").pack(side="left", padx=5)
        
        self.skin_preview_frame = tk.Frame(input_frame, bg=colors['frame_bg'])
        self.skin_preview_frame.pack(fill="both", expand=True, pady=20)
        
        self.skin_preview_label = tk.Label(self.skin_preview_frame, 
                                          text="Enter a username and click 'Preview' to see the skin",
                                          font=(font_family, 12), fg=colors['accent'], bg=colors['frame_bg'])
        self.skin_preview_label.pack(pady=30)
        
        # Skin resources
        links_frame = tk.Frame(self.main_frame, bg=colors['frame_bg'], relief="raised", borderwidth=1)
        links_frame.pack(fill="x", pady=20, padx=20)
        
        links_header = tk.Frame(links_frame, bg=colors['button_bg'], height=50)
        links_header.pack(fill="x")
        links_header.pack_propagate(False)
        
        links_title = tk.Label(links_header, text="🔗 Skin Resources", 
                             font=(font_family, 14, "bold"), fg="white", bg=colors['button_bg'])
        links_title.pack(pady=12)
        
        links_info = [
            ("SkinMC - Browse and download skins", "https://www.skinmc.net/"),
            ("MinecraftSkins - Large skin database", "https://www.minecraftskins.com/"),
            ("Planet Minecraft Skins", "https://www.planetminecraft.com/resources/skins/"),
            ("Skindex - Skin editor and gallery", "https://www.minecraftskins.com/")
        ]
        
        links_container = tk.Frame(links_frame, bg=colors['frame_bg'])
        links_container.pack(fill="x", padx=20, pady=20)
        
        for i, (text, url) in enumerate(links_info):
            ModernButton(links_container, text=text, width=350, height=35,
                        command=lambda u=url: webbrowser.open(u),
                        bg_color=colors['accent'], hover_color=colors['button_bg']).pack(pady=5)
    
    def preview_skin(self):
        username = self.username_var.get().strip()
        if not username:
            messagebox.showerror("Error", "Please enter a username")
            return
        
        self.log_action("Preview Skin", username)
        self.settings_manager.settings.skin_username = username
        self.settings_manager.save_settings()
        
        for widget in self.skin_preview_frame.winfo_children():
            widget.destroy()
        
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        loading_label = tk.Label(self.skin_preview_frame, text="Loading skin preview...",
                               font=(font_family, 12), fg=colors['accent'], bg=colors['frame_bg'])
        loading_label.pack(pady=20)
        
        def load_skin():
            try:
                skin_path = self.skin_manager.download_skin_preview(username)
                if skin_path and os.path.exists(skin_path):
                    self.root.after(0, lambda: self.display_skin_preview(skin_path, username))
                else:
                    self.root.after(0, lambda: self.show_skin_error(username))
            except Exception as e:
                logging.error(f"Error loading skin: {e}")
                self.root.after(0, lambda: self.show_skin_error(username))
        
        threading.Thread(target=load_skin, daemon=True).start()
    
    def download_full_skin(self):
        username = self.username_var.get().strip()
        if not username:
            messagebox.showerror("Error", "Please enter a username")
            return
        
        self.log_action("Download Full Skin", username)
        
        def download_skin():
            try:
                skin_path = self.skin_manager.download_full_skin(username)
                if skin_path:
                    self.root.after(0, lambda: messagebox.showinfo("Success", f"Full skin downloaded for {username}!"))
                else:
                    self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to download skin for {username}"))
            except Exception as e:
                logging.error(f"Error downloading full skin: {e}")
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to download skin: {e}"))
        
        threading.Thread(target=download_skin, daemon=True).start()
    
    def display_skin_preview(self, skin_path: str, username: str):
        for widget in self.skin_preview_frame.winfo_children():
            widget.destroy()
        
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        try:
            if PIL_AVAILABLE:
                image = Image.open(skin_path)
                image = image.resize((128, 128), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                
                preview_label = tk.Label(self.skin_preview_frame, image=photo, bg=colors['frame_bg'])
                preview_label.image = photo
                preview_label.pack(pady=15)
            
            info_label = tk.Label(self.skin_preview_frame, text=f"✅ Skin preview for: {username}", 
                                 font=(font_family, 14, "bold"), fg="#10b981", bg=colors['frame_bg'])
            info_label.pack(pady=10)
            
        except Exception as e:
            logging.error(f"Error displaying skin: {e}")
            self.show_skin_error(username)
    
    def show_skin_error(self, username: str):
        for widget in self.skin_preview_frame.winfo_children():
            widget.destroy()
        
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        error_label = tk.Label(self.skin_preview_frame, text=f"❌ Could not load skin for '{username}'",
                             font=(font_family, 12, "bold"), fg="#ef4444", bg=colors['frame_bg'])
        error_label.pack(pady=20)
        
        suggestion_label = tk.Label(self.skin_preview_frame, 
                                   text="Make sure the username is correct and has a custom skin",
                                   font=(font_family, 10), fg=colors['accent'], bg=colors['frame_bg'])
        suggestion_label.pack(pady=10)
    
    def open_skinmc(self):
        username = self.username_var.get().strip()
        if username:
            url = self.skin_manager.get_skinmc_url(username)
            webbrowser.open(url)
            self.log_action("Open SkinMC", username)
        else:
            webbrowser.open("https://www.skinmc.net/")
            self.log_action("Open SkinMC")
    
    def show_downloaded_skins(self):
        self.log_action("Show Downloaded Skins")
        if not self.skin_manager:
            self.show_minecraft_setup()
            return
            
        self.clear_main_frame()
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        # Header
        header_frame = GradientFrame(self.main_frame, 800, 80, colors['button_bg'], colors['accent'], 'horizontal')
        header_frame.pack(fill="x", pady=(0, 20))
        
        title_label = tk.Label(header_frame, text="🖼️ Downloaded Skins", 
                              font=(font_family, 20, "bold"), fg="white", bg=colors['button_bg'])
        title_label.place(x=30, y=25)
        
        # Action buttons
        button_frame = tk.Frame(self.main_frame, bg=colors['bg'])
        button_frame.pack(fill="x", pady=(0, 20), padx=20)
        
        ModernButton(button_frame, text="🔄 Refresh", command=self.show_downloaded_skins,
                    width=120, height=40, bg_color=colors['accent'], hover_color=colors['button_bg']).pack(side="left", padx=10)
        ModernButton(button_frame, text="📁 Open Folder", command=self.open_skins_folder,
                    width=140, height=40, bg_color="#f59e0b", hover_color="#d97706").pack(side="left", padx=10)
        
        # Skins list
        scrollable_frame = ScrollableFrame(self.main_frame)
        scrollable_frame.pack(fill="both", expand=True, padx=20)
        
        try:
            skins = self.skin_manager.get_downloaded_skins()
            
            if not skins:
                no_skins_frame = tk.Frame(scrollable_frame.scrollable_frame, bg=colors['frame_bg'], 
                                        relief="raised", borderwidth=2)
                no_skins_frame.pack(fill="x", pady=20, padx=20)
                
                no_skins_label = tk.Label(no_skins_frame, 
                                        text="👤 No skins downloaded.\nUse the Skin Manager to download some!", 
                                        font=(font_family, 16), fg=colors['fg'], bg=colors['frame_bg'], justify="center")
                no_skins_label.pack(pady=40)
                return
            
            for skin in skins:
                self.create_skin_item(scrollable_frame.scrollable_frame, skin)
                
        except Exception as e:
            logging.error(f"Error displaying skins: {e}")
            error_label = tk.Label(scrollable_frame.scrollable_frame, 
                                 text=f"❌ Error loading skins: {e}", 
                                 fg="#ef4444", bg=colors['bg'])
            error_label.pack(pady=20)
    
    def create_skin_item(self, parent, skin: Dict):
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        skin_frame = tk.Frame(parent, bg=colors['frame_bg'], relief="raised", borderwidth=1)
        skin_frame.pack(fill="x", pady=5, padx=10)
        
        # Skin preview if available
        preview_frame = tk.Frame(skin_frame, bg=colors['frame_bg'])
        preview_frame.pack(side="left", padx=20, pady=15)
        
        try:
            if PIL_AVAILABLE and os.path.exists(skin['file_path']):
                image = Image.open(skin['file_path'])
                image = image.resize((64, 64), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                
                preview_label = tk.Label(preview_frame, image=photo, bg=colors['frame_bg'])
                preview_label.image = photo
                preview_label.pack()
            else:
                placeholder_label = tk.Label(preview_frame, text="👤", 
                                           font=(font_family, 32), fg=colors['accent'], bg=colors['frame_bg'])
                placeholder_label.pack()
        except:
            placeholder_label = tk.Label(preview_frame, text="👤", 
                                       font=(font_family, 32), fg=colors['accent'], bg=colors['frame_bg'])
            placeholder_label.pack()
        
        # Skin info section
        info_frame = tk.Frame(skin_frame, bg=colors['frame_bg'])
        info_frame.pack(side="left", fill="both", expand=True, padx=20, pady=15)
        
        # Username and type
        type_icon = "🖼️" if skin['type'] == 'preview' else "👤"
        name_label = tk.Label(info_frame, text=f"{type_icon} {skin['username']}", 
                             font=(font_family, 14, "bold"), fg=colors['fg'], bg=colors['frame_bg'])
        name_label.pack(anchor="w")
        
        # Type and size
        size_kb = skin['file_size'] / 1024 if skin['file_size'] > 0 else 0
        details_text = f"📋 Type: {skin['type'].title()} | 💾 {size_kb:.1f} KB"
        details_label = tk.Label(info_frame, text=details_text, 
                               font=(font_family, 9), fg=colors['fg'], bg=colors['frame_bg'])
        details_label.pack(anchor="w")
        
        # Download date
        date_text = f"📅 Downloaded: {skin['downloaded_date'][:10]}"
        date_label = tk.Label(info_frame, text=date_text, 
                            font=(font_family, 9), fg=colors['accent'], bg=colors['frame_bg'])
        date_label.pack(anchor="w")
        
        # Buttons section
        button_frame = tk.Frame(skin_frame, bg=colors['frame_bg'])
        button_frame.pack(side="right", padx=20, pady=15)
        
        ModernButton(button_frame, text="📁 Open", width=80, height=35,
                    command=lambda: self.open_skin_file(skin['file_path']), 
                    bg_color=colors['accent'], hover_color=colors['button_bg']).pack(side="left", padx=5)
        
        ModernButton(button_frame, text="🗑️ Remove", width=80, height=35,
                    command=lambda: self.remove_skin(skin['username'], skin['type']), 
                    bg_color="#ef4444", hover_color="#dc2626").pack(side="left", padx=5)
    
    def show_color_customizer(self):
        self.log_action("Show Color Customizer")
        if not self.settings_manager:
            self.show_minecraft_setup()
            return
            
        self.clear_main_frame()
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        # Header
        header_frame = GradientFrame(self.main_frame, 800, 80, colors['button_bg'], colors['accent'], 'horizontal')
        header_frame.pack(fill="x", pady=(0, 20))
        
        title_label = tk.Label(header_frame, text="🎨 Customize Colors", 
                              font=(font_family, 20, "bold"), fg="white", bg=colors['button_bg'])
        title_label.place(x=30, y=25)
        
        # Color customizer content
        customizer_scroll = ScrollableFrame(self.main_frame)
        customizer_scroll.pack(fill="both", expand=True, padx=20)
        
        customizer_frame = customizer_scroll.scrollable_frame
        
        # Color scheme settings
        scheme_frame = tk.LabelFrame(customizer_frame, text="Color Scheme", 
                                   font=(font_family, 12, "bold"), bg=colors['frame_bg'], fg=colors['fg'])
        scheme_frame.pack(fill="x", pady=10, padx=10)
        
        color_options = [
            ("Primary Color", "primary"),
            ("Secondary Color", "secondary"),
            ("Background Color", "background"),
            ("Surface Color", "surface"),
            ("Text Color", "text"),
            ("Accent Color", "accent"),
            ("Error Color", "error"),
            ("Success Color", "success"),
            ("Warning Color", "warning")
        ]
        
        self.color_vars = {}
        
        for i, (label, key) in enumerate(color_options):
            color_frame = tk.Frame(scheme_frame, bg=colors['frame_bg'])
            color_frame.pack(fill="x", padx=10, pady=5)
            
            tk.Label(color_frame, text=label + ":", font=(font_family, 11),
                    fg=colors['fg'], bg=colors['frame_bg']).pack(side="left", anchor="w", padx=(0, 20))
            
            current_color = getattr(self.settings_manager.settings.color_scheme, key)
            self.color_vars[key] = tk.StringVar(value=current_color)
            
            color_display = tk.Label(color_frame, text="     ", bg=current_color, 
                                   relief="raised", borderwidth=2)
            color_display.pack(side="left", padx=(0, 10))
            
            color_entry = ttk.Entry(color_frame, textvariable=self.color_vars[key], width=10)
            color_entry.pack(side="left", padx=(0, 10))
            
            ModernButton(color_frame, text="Choose", width=80, height=30,
                        command=lambda k=key, d=color_display: self.choose_color(k, d),
                        bg_color=colors['accent'], hover_color=colors['button_bg']).pack(side="left", padx=5)
        
        # Action buttons
        action_frame = tk.Frame(customizer_frame, bg=colors['bg'])
        action_frame.pack(fill="x", pady=20, padx=10)
        
        ModernButton(action_frame, text="💾 Apply Colors", command=self.apply_custom_colors,
                    width=150, height=40, bg_color="#10b981", hover_color="#059669").pack(side="left", padx=10)
        ModernButton(action_frame, text="🔄 Reset to Default", command=self.reset_colors,
                    width=150, height=40, bg_color="#ef4444", hover_color="#dc2626").pack(side="left", padx=10)
        ModernButton(action_frame, text="📋 Preview", command=self.preview_colors,
                    width=120, height=40, bg_color=colors['accent'], hover_color=colors['button_bg']).pack(side="left", padx=10)
    
    def choose_color(self, key: str, display_label: tk.Label):
        self.log_action("Choose Color", key)
        current_color = self.color_vars[key].get()
        color = colorchooser.askcolor(color=current_color, title=f"Choose {key.title()} Color")
        
        if color[1]:  # If a color was selected
            self.color_vars[key].set(color[1])
            display_label.configure(bg=color[1])
    
    def apply_custom_colors(self):
        self.log_action("Apply Custom Colors")
        try:
            # Update color scheme
            for key, var in self.color_vars.items():
                setattr(self.settings_manager.settings.color_scheme, key, var.get())
            
            # Set theme to custom
            self.settings_manager.settings.theme = "custom"
            self.settings_manager.save_settings()
            
            messagebox.showinfo("Colors Applied", "Custom colors applied! Please restart the application to see all changes.")
            
        except Exception as e:
            logging.error(f"Error applying colors: {e}")
            messagebox.showerror("Error", f"Failed to apply colors: {e}")
    
    def reset_colors(self):
        self.log_action("Reset Colors")
        if messagebox.askyesno("Reset Colors", "Reset all colors to default values?"):
            default_scheme = ColorScheme()
            for key in self.color_vars.keys():
                default_color = getattr(default_scheme, key)
                self.color_vars[key].set(default_color)
                
            # Update display labels
            for widget in self.main_frame.winfo_children():
                if isinstance(widget, ScrollableFrame):
                    self.update_color_displays(widget.scrollable_frame)
    
    def update_color_displays(self, parent):
        for child in parent.winfo_children():
            if hasattr(child, 'winfo_children'):
                for grandchild in child.winfo_children():
                    if isinstance(grandchild, tk.Frame):
                        for label in grandchild.winfo_children():
                            if isinstance(label, tk.Label) and label.cget('text') == "     ":
                                # Find corresponding color key
                                for key, var in self.color_vars.items():
                                    if var.get() in str(label.cget('bg')):
                                        label.configure(bg=var.get())
    
    def preview_colors(self):
        self.log_action("Preview Colors")
        messagebox.showinfo("Preview", "Color preview functionality would show a sample window with the selected colors.")
    
    def show_settings(self):
        self.log_action("Show Settings")
        if not self.settings_manager:
            self.show_minecraft_setup()
            return
            
        self.clear_main_frame()
        colors = self.style_manager.colors
        font_family = "Segoe UI" if platform.system() == "Windows" else ("SF Pro Display" if platform.system() == "Darwin" else "Ubuntu")
        
        # Header
        header_frame = GradientFrame(self.main_frame, 800, 80, colors['button_bg'], colors['accent'], 'horizontal')
        header_frame.pack(fill="x", pady=(0, 20))
        
        title_label = tk.Label(header_frame, text="⚙️ Settings", 
                              font=(font_family, 20, "bold"), fg="white", bg=colors['button_bg'])
        title_label.place(x=30, y=25)
        
        # Settings content
        settings_scroll = ScrollableFrame(self.main_frame)
        settings_scroll.pack(fill="both", expand=True, padx=20)
        
        settings_frame = settings_scroll.scrollable_frame
        
        # General Settings
        general_frame = tk.LabelFrame(settings_frame, text="General Settings", 
                                    font=(font_family, 12, "bold"), bg=colors['frame_bg'], fg=colors['fg'])
        general_frame.pack(fill="x", pady=10, padx=10)
        
        # Minecraft Path
        path_frame = tk.Frame(general_frame, bg=colors['frame_bg'])
        path_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Label(path_frame, text="Minecraft Path:", font=(font_family, 11), 
                fg=colors['fg'], bg=colors['frame_bg']).pack(side="left")
        
        self.path_var = tk.StringVar(value=self.settings_manager.settings.minecraft_path)
        path_entry = ttk.Entry(path_frame, textvariable=self.path_var, width=50)
        path_entry.pack(side="left", padx=10)
        
        ModernButton(path_frame, text="Browse", command=self.browse_minecraft_path,
                    width=80, height=30, bg_color=colors['accent']).pack(side="left", padx=5)
        
        # Theme Selection - MOVED HERE FROM HEADER
        theme_frame = tk.Frame(general_frame, bg=colors['frame_bg'])
        theme_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Label(theme_frame, text="Theme:", font=(font_family, 11), 
                fg=colors['fg'], bg=colors['frame_bg']).pack(side="left")
        
        self.theme_var = tk.StringVar(value=self.settings_manager.settings.theme)
        theme_combo = ttk.Combobox(theme_frame, textvariable=self.theme_var, 
                                  values=["modern", "dark", "light", "custom"], state="readonly", width=15)
        theme_combo.pack(side="left", padx=10)
        theme_combo.bind("<<ComboboxSelected>>", self.change_theme)
        
        # Debug Mode
        debug_frame = tk.Frame(general_frame, bg=colors['frame_bg'])
        debug_frame.pack(fill="x", padx=10, pady=5)
        
        self.debug_var = tk.BooleanVar(value=self.settings_manager.settings.debug_mode)
        debug_check = ttk.Checkbutton(debug_frame, text="Enable Debug Mode (Creates detailed log files)", 
                                    variable=self.debug_var, command=self.toggle_debug_mode)
        debug_check.pack(side="left")
        
        # Other settings
        other_frame = tk.Frame(general_frame, bg=colors['frame_bg'])
        other_frame.pack(fill="x", padx=10, pady=5)
        
        self.animations_var = tk.BooleanVar(value=self.settings_manager.settings.animations_enabled)
        animations_check = ttk.Checkbutton(other_frame, text="Enable Animations", 
                                         variable=self.animations_var, command=self.toggle_animations)
        animations_check.pack(side="left")
        
        # Auto backup
        backup_frame = tk.Frame(general_frame, bg=colors['frame_bg'])
        backup_frame.pack(fill="x", padx=10, pady=5)
        
        self.backup_var = tk.BooleanVar(value=self.settings_manager.settings.auto_backup)
        backup_check = ttk.Checkbutton(backup_frame, text="Enable Auto Backup", 
                                     variable=self.backup_var, command=self.toggle_backup)
        backup_check.pack(side="left")
        
        # Launcher Settings
        launcher_frame = tk.LabelFrame(settings_frame, text="Launcher Settings", 
                                     font=(font_family, 12, "bold"), bg=colors['frame_bg'], fg=colors['fg'])
        launcher_frame.pack(fill="x", pady=10, padx=10)
        
        # Launcher Path
        launcher_path_frame = tk.Frame(launcher_frame, bg=colors['frame_bg'])
        launcher_path_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Label(launcher_path_frame, text="Launcher Path:", font=(font_family, 11), 
                fg=colors['fg'], bg=colors['frame_bg']).pack(side="left")
        
        self.launcher_path_var = tk.StringVar(value=self.settings_manager.settings.launcher_path)
        launcher_entry = ttk.Entry(launcher_path_frame, textvariable=self.launcher_path_var, width=50)
        launcher_entry.pack(side="left", padx=10)
        
        ModernButton(launcher_path_frame, text="Browse", command=self.browse_launcher_path,
                    width=80, height=30, bg_color=colors['accent']).pack(side="left", padx=5)
        
        ModernButton(launcher_path_frame, text="Auto-Detect", command=self.auto_detect_launcher,
                    width=100, height=30, bg_color="#10b981", hover_color="#059669").pack(side="left", padx=5)
        
        # Save button
        save_frame = tk.Frame(settings_frame, bg=colors['bg'])
        save_frame.pack(fill="x", pady=20, padx=10)
        
        ModernButton(save_frame, text="💾 Save Settings", command=self.save_settings,
                    width=150, height=40, bg_color="#10b981", hover_color="#059669").pack()
    
    def change_theme(self, event=None):
        if not self.settings_manager:
            return
            
        new_theme = self.theme_var.get()
        self.log_action("Change Theme", new_theme)
        
        if new_theme == "custom":
            self.show_color_customizer()
            return
        
        self.settings_manager.settings.theme = new_theme
        self.settings_manager.save_settings()
        
        messagebox.showinfo("Theme Changed", "Please restart the application to apply the new theme.")
    
    def browse_minecraft_path(self):
        self.log_action("Browse Minecraft Path")
        path = filedialog.askdirectory(title="Select Minecraft Directory")
        if path:
            self.path_var.set(path)
            self.log_action("Minecraft Path Selected", path)
    
    def browse_launcher_path(self):
        self.log_action("Browse Launcher Path")
        if platform.system() == "Windows":
            path = filedialog.askopenfilename(title="Select Minecraft Launcher", 
                                            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")])
        else:
            path = filedialog.askopenfilename(title="Select Minecraft Launcher")
        
        if path:
            self.launcher_path_var.set(path)
            self.log_action("Launcher Path Selected", path)
    
    def auto_detect_launcher(self):
        self.log_action("Auto-Detect Launcher")
        launcher_path = MinecraftDetector.detect_launcher_path()
        if launcher_path:
            self.launcher_path_var.set(launcher_path)
            self.log_action("Launcher Auto-Detected", launcher_path)
            messagebox.showinfo("Success", f"Launcher detected at: {launcher_path}")
        else:
            self.log_action("Launcher Auto-Detect Failed")
            messagebox.showerror("Not Found", "Could not automatically detect Minecraft launcher.")
    
    def toggle_debug_mode(self):
        debug_enabled = self.debug_var.get()
        self.settings_manager.settings.debug_mode = debug_enabled
        self.settings_manager.save_settings()
        
        # Reinitialize logging
        self.setup_logging()
        
        if debug_enabled:
            self.log_action("Debug Mode Enabled")
            messagebox.showinfo("Debug Mode", "Debug mode enabled. Detailed log files will be created.")
        else:
            messagebox.showinfo("Debug Mode", "Debug mode disabled. No log files will be created.")
    
    def toggle_animations(self):
        self.settings_manager.settings.animations_enabled = self.animations_var.get()
        self.settings_manager.save_settings()
        self.log_action("Toggle Animations", str(self.animations_var.get()))
    
    def toggle_backup(self):
        self.settings_manager.settings.auto_backup = self.backup_var.get()
        self.settings_manager.save_settings()
        self.log_action("Toggle Auto Backup", str(self.backup_var.get()))
    
    def save_settings(self):
        self.log_action("Save Settings")
        self.settings_manager.settings.minecraft_path = self.path_var.get()
        self.settings_manager.settings.launcher_path = self.launcher_path_var.get()
        self.settings_manager.save_settings()
        messagebox.showinfo("Settings", "Settings saved successfully!")
    
    # Utility methods for various actions
    def toggle_mod(self, mod: ModInfo):
        self.log_action("Toggle Mod", f"{mod.name} - {'Disable' if mod.enabled else 'Enable'}")
        try:
            self.mod_manager.toggle_mod(mod)
            messagebox.showinfo("Success", f"Mod {'disabled' if not mod.enabled else 'enabled'} successfully!")
            self.show_installed_mods()  # Refresh view
        except Exception as e:
            logging.error(f"Error toggling mod: {e}")
            messagebox.showerror("Error", f"Failed to toggle mod: {e}")
    
    def remove_mod(self, mod: ModInfo):
        self.log_action("Remove Mod", mod.name)
        if messagebox.askyesno("Confirm", f"Are you sure you want to remove '{mod.name}'?"):
            try:
                self.mod_manager.remove_mod(mod)
                messagebox.showinfo("Success", "Mod removed successfully!")
                self.show_installed_mods()  # Refresh view
            except Exception as e:
                logging.error(f"Error removing mod: {e}")
                messagebox.showerror("Error", f"Failed to remove mod: {e}")
    
    def create_profile(self):
        self.log_action("Create Profile")
        # Simple profile creation dialog
        profile_name = simpledialog.askstring("Create Profile", "Enter profile name:")
        if profile_name:
            try:
                new_profile = ModProfile(
                    name=profile_name,
                    description=f"Profile created on {datetime.now().strftime('%Y-%m-%d')}",
                    minecraft_version="Latest",
                    mod_loader="Any",
                    mods=[],
                    created_date=datetime.now().isoformat()
                )
                self.mod_manager.profile_manager.save_profile(new_profile)
                self.log_action("Profile Created", profile_name)
                messagebox.showinfo("Success", f"Profile '{profile_name}' created successfully!")
                self.show_mod_profiles()  # Refresh view
            except Exception as e:
                logging.error(f"Error creating profile: {e}")
                messagebox.showerror("Error", f"Failed to create profile: {e}")
    
    def switch_profile(self, profile: ModProfile):
        self.log_action("Switch Profile", profile.name)
        try:
            self.settings_manager.settings.current_profile = profile.name.lower()
            self.settings_manager.save_settings()
            messagebox.showinfo("Success", f"Switched to profile '{profile.name}'!")
            self.show_mod_profiles()  # Refresh view
        except Exception as e:
            logging.error(f"Error switching profile: {e}")
            messagebox.showerror("Error", f"Failed to switch profile: {e}")
    
    def edit_profile(self, profile: ModProfile):
        self.log_action("Edit Profile", profile.name)
        messagebox.showinfo("Edit Profile", f"Profile editing for '{profile.name}' would open here.")
    
    def delete_profile(self, profile: ModProfile):
        self.log_action("Delete Profile", profile.name)
        if messagebox.askyesno("Confirm", f"Are you sure you want to delete profile '{profile.name}'?"):
            try:
                self.mod_manager.profile_manager.delete_profile(profile.name)
                messagebox.showinfo("Success", f"Profile '{profile.name}' deleted successfully!")
                self.show_mod_profiles()  # Refresh view
            except Exception as e:
                logging.error(f"Error deleting profile: {e}")
                messagebox.showerror("Error", f"Failed to delete profile: {e}")
    
    def create_modpack(self):
        self.log_action("Create Modpack")
        messagebox.showinfo("Create Modpack", "Modpack creation wizard would open here.")
    
    def open_modpack(self, path: str):
        self.log_action("Open Modpack", path)
        if os.path.exists(path):
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
    
    def remove_modpack(self, name: str):
        self.log_action("Remove Modpack", name)
        if messagebox.askyesno("Confirm", f"Are you sure you want to remove modpack '{name}'?"):
            messagebox.showinfo("Success", f"Modpack '{name}' would be removed.")
    
    def add_resource_pack(self):
        self.log_action("Add Resource Pack")
        file_path = filedialog.askopenfilename(
            title="Select Resource Pack",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")]
        )
        
        if file_path:
            try:
                dest_path = self.mod_manager.vm.resource_packs_path / Path(file_path).name
                shutil.copy2(file_path, dest_path)
                self.log_action("Resource Pack Added", Path(file_path).name)
                messagebox.showinfo("Success", "Resource pack added successfully!")
                self.show_resource_packs()  # Refresh view
            except Exception as e:
                logging.error(f"Failed to add resource pack: {e}")
                messagebox.showerror("Error", f"Failed to add resource pack: {e}")
    
    def open_resource_pack(self, path: str):
        self.log_action("Open Resource Pack", path)
        if os.path.exists(path):
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
    
    def remove_resource_pack(self, name: str):
        self.log_action("Remove Resource Pack", name)
        if messagebox.askyesno("Confirm", f"Are you sure you want to remove resource pack '{name}'?"):
            try:
                pack_path = self.mod_manager.vm.resource_packs_path / name
                if pack_path.exists():
                    if pack_path.is_dir():
                        shutil.rmtree(pack_path)
                    else:
                        pack_path.unlink()
                    messagebox.showinfo("Success", "Resource pack removed successfully!")
                    self.show_resource_packs()  # Refresh view
            except Exception as e:
                logging.error(f"Error removing resource pack: {e}")
                messagebox.showerror("Error", f"Failed to remove resource pack: {e}")
    
    def open_skin_file(self, path: str):
        self.log_action("Open Skin File", path)
        if os.path.exists(path):
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
    
    def remove_skin(self, username: str, skin_type: str):
        self.log_action("Remove Skin", f"{username} - {skin_type}")
        if messagebox.askyesno("Confirm", f"Are you sure you want to remove {username}'s {skin_type} skin?"):
            try:
                skin_file = self.skin_manager.vm.skins_path / f"{username}_{skin_type}.png"
                if skin_file.exists():
                    skin_file.unlink()
                    messagebox.showinfo("Success", "Skin removed successfully!")
                    self.show_downloaded_skins()  # Refresh view
            except Exception as e:
                logging.error(f"Error removing skin: {e}")
                messagebox.showerror("Error", f"Failed to remove skin: {e}")
    
    # Folder opening methods
    def open_mods_folder(self):
        self.log_action("Open Mods Folder")
        if self.mod_manager and self.mod_manager.vm.mods_path.exists():
            if platform.system() == "Windows":
                os.startfile(str(self.mod_manager.vm.mods_path))
            elif platform.system() == "Darwin":
                subprocess.run(["open", str(self.mod_manager.vm.mods_path)])
            else:
                subprocess.run(["xdg-open", str(self.mod_manager.vm.mods_path)])
    
    def open_modpacks_folder(self):
        self.log_action("Open Modpacks Folder")
        if self.mod_manager and self.mod_manager.vm.modpacks_path.exists():
            if platform.system() == "Windows":
                os.startfile(str(self.mod_manager.vm.modpacks_path))
            elif platform.system() == "Darwin":
                subprocess.run(["open", str(self.mod_manager.vm.modpacks_path)])
            else:
                subprocess.run(["xdg-open", str(self.mod_manager.vm.modpacks_path)])
    
    def open_resource_packs_folder(self):
        self.log_action("Open Resource Packs Folder")
        if self.mod_manager and self.mod_manager.vm.resource_packs_path.exists():
            if platform.system() == "Windows":
                os.startfile(str(self.mod_manager.vm.resource_packs_path))
            elif platform.system() == "Darwin":
                subprocess.run(["open", str(self.mod_manager.vm.resource_packs_path)])
            else:
                subprocess.run(["xdg-open", str(self.mod_manager.vm.resource_packs_path)])
    
    def open_skins_folder(self):
        self.log_action("Open Skins Folder")
        if self.skin_manager and self.skin_manager.vm.skins_path.exists():
            if platform.system() == "Windows":
                os.startfile(str(self.skin_manager.vm.skins_path))
            elif platform.system() == "Darwin":
                subprocess.run(["open", str(self.skin_manager.vm.skins_path)])
            else:
                subprocess.run(["xdg-open", str(self.skin_manager.vm.skins_path)])
    
    # Launcher functionality
    def launch_minecraft(self):
        self.log_action("Launch Minecraft")
        if not self.settings_manager.settings.launcher_path:
            messagebox.showerror("Error", "Minecraft launcher not found. Please configure it in Settings.")
            return
        
        try:
            launcher_path = self.settings_manager.settings.launcher_path
            
            if platform.system() == "Windows":
                subprocess.Popen([launcher_path])
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", launcher_path])
            else:  # Linux
                subprocess.Popen([launcher_path])
            
            messagebox.showinfo("Success", "Minecraft launcher started!")
            
        except Exception as e:
            logging.error(f"Error launching Minecraft: {e}")
            messagebox.showerror("Error", f"Failed to launch Minecraft: {e}")
    
    def launch_profile(self):
        self.log_action("Launch Profile")
        messagebox.showinfo("Launch Profile", "Profile-specific launching would be implemented here.")
    
    def open_minecraft_folder(self):
        self.log_action("Open Minecraft Folder")
        if self.minecraft_path:
            if platform.system() == "Windows":
                os.startfile(self.minecraft_path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", self.minecraft_path])
            else:
                subprocess.run(["xdg-open", self.minecraft_path])
    
    def add_mod(self):
        self.log_action("Add Mod")
        if not self.mod_manager:
            messagebox.showerror("Error", "Minecraft not configured")
            return
        
        file_path = filedialog.askopenfilename(
            title="Select Mod File",
            filetypes=[("JAR files", "*.jar"), ("All files", "*.*")]
        )
        
        if file_path:
            try:
                dest_path = self.mod_manager.vm.mods_path / Path(file_path).name
                shutil.copy2(file_path, dest_path)
                self.log_action("Mod Added", Path(file_path).name)
                messagebox.showinfo("Success", "✅ Mod added successfully!")
                if hasattr(self, 'current_view') and self.current_view == 'installed_mods':
                    self.show_installed_mods()
            except Exception as e:
                logging.error(f"Failed to add mod: {e}")
                messagebox.showerror("Error", f"❌ Failed to add mod: {e}")
    
    def on_closing(self):
        self.log_action("Application Closing")
        try:
            if self.settings_manager:
                self.settings_manager.settings.window_geometry = self.root.geometry()
                self.settings_manager.save_settings()
            logging.info("Application closed successfully")
        except Exception as e:
            logging.error(f"Error saving settings on close: {e}")
        finally:
            self.root.destroy()
    
    def run(self):
        try:
            if self.settings_manager and self.settings_manager.settings.window_geometry:
                self.root.geometry(self.settings_manager.settings.window_geometry)
            
            self.log_action("Application Started")
            self.root.mainloop()
        except Exception as e:
            logging.error(f"Fatal error: {e}")
            messagebox.showerror("Fatal Error", f"Application crashed: {e}")

if __name__ == "__main__":
    try:
        app = MinecraftModManager()
        app.run()
    except Exception as e:
        print(f"Failed to start application: {e}")
        logging.error(f"Failed to start application: {e}")
        messagebox.showerror("Startup Error", f"Failed to start application: {e}")
