"""Program entry point with friendly checks for missing requirements."""
from __future__ import annotations

import sys


def main() -> int:
    if sys.version_info < (3, 9):
        print("Vanquish's Mod Manager needs Python 3.9 or newer.", file=sys.stderr)
        return 1
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("Tkinter is not installed for this Python.\n"
              "  Debian/Ubuntu:  sudo apt install python3-tk\n"
              "  Fedora:         sudo dnf install python3-tkinter\n"
              "  Arch:           sudo pacman -S tk\n"
              "  macOS Homebrew: brew install python-tk\n"
              "  Windows/macOS:  use the installer from python.org (includes Tk)", file=sys.stderr)
        return 1
    from .gui.app import main as gui_main
    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
