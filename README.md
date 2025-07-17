Minecraft Mod Manager

🎮 Overview
The Minecraft Mod Manager is a comprehensive desktop application built with Python and Tkinter, designed to simplify the management of Minecraft mods, mod profiles, resource packs, and even player skins. It provides a modern, intuitive graphical interface to help Minecraft players easily organize their game files, switch between different mod setups, and enhance their gaming experience without manually digging through game folders.

✨ Features
Automatic Minecraft Detection: Automatically detects your Minecraft installation directory on Windows, macOS, and Linux.

Mod Management:

View all installed mods (both enabled and disabled).

Enable/disable mods with a single click.

Remove unwanted mods.

Add new mods by browsing your local files.

Extracts mod information (version, loader, Minecraft version, description) from .jar files.

Mod Profiles:

Create and manage multiple mod profiles for different gameplay experiences (e.g., "Vanilla+", "Tech Modpack", "Adventure Map").

Switch between profiles easily.

Resource Pack Management:

List and manage installed resource packs.

Add and remove resource packs.

Skin Manager:

Download and preview Minecraft skins directly from usernames.

View a gallery of downloaded skins.

Quick links to popular skin resources like SkinMC.

Popular Mods & Modpacks: Browse a curated list of popular mods and modpacks with links to their download pages (CurseForge, Modrinth).

Downloaded Modpacks: Detects and lists modpacks installed via popular launchers like CurseForge, MultiMC, ATLauncher, and Technic Launcher.

Customizable Themes: Switch between modern, dark, light, and custom color themes.

Settings: Configure Minecraft path, launcher path, enable/disable animations, auto-backup, and debug mode.

Direct Launcher Integration: Launch Minecraft directly from the application.

Folder Quick Access: Quickly open your .minecraft folder, mods folder, resource packs folder, and skins folder.

Logging: Detailed logging for debugging purposes (when enabled).

🚀 Getting Started
To run this application, follow these steps:

Prerequisites
Python 3.x installed on your system.

pip (Python package installer), which usually comes with Python.

Installation
There are two ways to get the application up and running:

Option 1: Clone the Repository (Recommended for Developers)
Clone the repository:

git clone <repository_url>
cd <repository_name> # Replace with your repository name

Install required Python packages:

pip install Pillow requests

Option 2: Download the Python File Directly
Download the modmanager 2.py file:

Go to the GitHub repository page.

Click on the modmanager 2.py file.

Click the "Raw" button.

Right-click on the page and select "Save as..." to save the file to your desired location (e.g., your Desktop or a dedicated project folder).

Open your terminal or command prompt:

Windows: Press Win + R, type cmd, and press Enter.

macOS: Open "Terminal" from Applications/Utilities.

Linux: Open your preferred terminal application.

Navigate to the directory where you saved modmanager 2.py:
If you saved it to your Desktop, for example:

cd Desktop

(Replace Desktop with the actual path if different.)

Install required Python packages:

pip install Pillow requests

The application will also attempt to install these dependencies automatically on first run, but it's good practice to install them beforehand.

Running the Application
Execute the Python script:

From your terminal or command prompt, in the directory where modmanager 2.py is located, run:

python "modmanager.py"

First-time Setup:

Upon the first launch, the application will attempt to auto-detect your Minecraft installation.

If auto-detection fails, you will be prompted to manually select your .minecraft directory. Navigate to your Minecraft installation folder (e.g., C:\Users\YourUser\AppData\Roaming\.minecraft on Windows, ~/Library/Application Support/minecraft on macOS, or ~/.minecraft on Linux) and select it.

The application will save this path in its settings for future use.

📁 Project Structure
The main logic is contained within the modmanager 2.py file, which includes several classes for different functionalities:

ModInfo, ModProfile, ColorScheme, Settings: Data classes for managing mod, profile, and application settings.

PopularModsData: Contains static data for popular mods and modpacks.

VanquishModManager: Manages core directories and paths for the application.

AnimatedWidget, ModernButton, GradientFrame, ModernStyle, ScrollableFrame: Custom Tkinter widgets and styling for a modern UI.

MinecraftDetector: Utility for detecting Minecraft installation paths, versions, and mod loaders.

ProfileManager: Handles saving, loading, and managing mod profiles.

ModManager: Core logic for managing installed mods, resource packs, and detecting downloaded modpacks.

SkinManager: Handles downloading and managing Minecraft player skins.

SettingsManager: Manages application settings persistence.

MinecraftModManager: The main application class, initializing the UI and integrating all other managers.

🛠️ Development Notes
UI/UX: The application uses custom Tkinter widgets and styling to achieve a modern look and feel, including gradients, rounded buttons, and animations.

Platform Compatibility: Designed to work across Windows, macOS, and Linux, with platform-specific path detection and command execution.

Error Handling: Includes basic error handling and logging to modmanager.log (when debug mode is enabled in settings).

Dependencies: Relies on Pillow for image processing (skin previews) and requests for web interactions (downloading skins).

🤝 Contributing
Contributions are welcome! If you have suggestions for improvements, bug fixes, or new features, please feel free to:

Fork the repository.

Create a new branch (git checkout -b feature/your-feature).

Make your changes.

Commit your changes (git commit -m 'Add new feature').

Push to the branch (git push origin feature/your-feature).

Open a Pull Request.

📝 Further Notes from the Developer
This project is still in active development, and I'm continuously working to improve it. It currently serves primarily as a learning project for Python development and is not yet intended to be a production-ready client.

Current Development Focus:
UI/UX Refinements: Actively working on improving the button styling and overall user interface for a more polished look.

Skin Manager Enhancements: Improving the reliability and functionality of the skin manager for downloading and previewing skins.

Mod Link Integration: Implementing direct links to specific mod pages on CurseForge and Modrinth, rather than just their home pages.

Future Plans:
Standalone Executable: The goal is to package this application into a standalone .exe (or equivalent for other OS) that handles its own dependency installation.

Complete UI Overhaul: A significant redesign of the user interface to enhance aesthetics and usability.

New Features:

Friend list functionality.

Options to join friends' games directly.

Mini-Client Development: Evolving this manager into a small, lightweight Minecraft client with integrated mod management capabilities.
