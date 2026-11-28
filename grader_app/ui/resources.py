"""Location of bundled files (the user guide), in development and in the packaged app."""
import sys
from pathlib import Path


def resource_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else Path(__file__).resolve().parents[2]
