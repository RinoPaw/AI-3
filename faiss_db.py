"""Backward-compatible wrapper for the legacy module name."""

from pathlib import Path
import sys


SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mudan.vector_store import *  # noqa: F401,F403,E402
