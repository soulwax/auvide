"""auvide - AI video upscaler + vibrant HDR10 remapper.

The single source of truth for the engine: everything the CLI, the legacy
Tkinter GUI, and the Tauri desktop app run is this package. See cli.py for
the pipeline entry point.
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("auvide")
except PackageNotFoundError:
    # Supports direct source-tree execution before an editable/package install.
    __version__ = "0.0.0+unknown"
