"""Allow `python -m vanquish`."""
import sys

from .cli import main

sys.exit(main())
