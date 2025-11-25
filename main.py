import sys
import subprocess
import importlib.util
import os

# --- Dependency Auto-Installation ---
REQUIRED_PACKAGES = ["customtkinter", "requests", "pillow", "packaging"]

def check_and_install_packages():
    print("Checking dependencies...")
    for package in REQUIRED_PACKAGES:
        spec = importlib.util.find_spec(package)
        if spec is None:
            print(f"Installing missing package: {package}")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            except subprocess.CalledProcessError as e:
                print(f"Failed to install {package}: {e}")
                sys.exit(1)
    print("All dependencies installed.")

if __name__ == "__main__":
    check_and_install_packages()

    try:
        from config import Config
        from backend import ModManager
        from gui import App
        conf = Config()
        mgr = ModManager(conf)
        app = App(conf, mgr)
        app.mainloop()
    except Exception as e:
        print(f"Critical Error: {e}")
        input("Press Enter to exit...")