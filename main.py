#!/usr/bin/env python3
"""Start Vanquish's Mod Manager:  python3 main.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vanquish.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
